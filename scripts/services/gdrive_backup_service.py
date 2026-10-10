import io
import os
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from django.conf import settings
from django.utils import timezone

from scripts.models import Script
from scripts.services.pdf_export import generate_screenplay_pdf

logger = logging.getLogger(__name__)

GOOGLE_DRIVE_FOLDER_NAME = 'KadhaScript Backups'
GOOGLE_DRIVE_SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/drive',
]
BACKUP_RETENTION_COUNT = 30


class GoogleDriveBackupError(Exception):
    """Base exception for Google Drive backup operations."""
    pass


class GoogleDriveAuthError(GoogleDriveBackupError):
    """Raised when authentication with Google Drive fails or credentials are missing."""
    pass


def get_gdrive_service():
    """
    Initializes and returns an authorized Google Drive v3 API client.
    Supports credentials from:
    1. GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON (JSON string in env var)
    2. GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE (path to JSON file in env var)
    3. GOOGLE_APPLICATION_CREDENTIALS (standard GCP credentials file)
    """
    try:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account
    except ImportError as e:
        logger.error("google-api-python-client or google-auth not installed: %s", str(e))
        raise GoogleDriveAuthError("Google Drive client libraries are not installed.") from e

    sa_json_raw = os.getenv('GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON')
    sa_file_path = os.getenv('GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE') or os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

    creds = None

    if sa_json_raw:
        try:
            sa_info = json.loads(sa_json_raw)
            creds = service_account.Credentials.from_service_account_info(
                sa_info,
                scopes=GOOGLE_DRIVE_SCOPES
            )
        except Exception as e:
            logger.error("Failed to parse GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON: %s", str(e))
            raise GoogleDriveAuthError(f"Invalid service account JSON: {str(e)}") from e

    elif sa_file_path and os.path.exists(sa_file_path):
        try:
            creds = service_account.Credentials.from_service_account_file(
                sa_file_path,
                scopes=GOOGLE_DRIVE_SCOPES
            )
        except Exception as e:
            logger.error("Failed to load credentials from file %s: %s", sa_file_path, str(e))
            raise GoogleDriveAuthError(f"Failed to load service account file: {str(e)}") from e

    if not creds:
        raise GoogleDriveAuthError(
            "No Google Drive credentials found. Please set GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON or "
            "GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE in environment variables."
        )

    try:
        service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        return service
    except Exception as e:
        logger.error("Failed to build Google Drive service: %s", str(e))
        raise GoogleDriveAuthError(f"Failed to initialize Drive service: {str(e)}") from e


def get_or_create_backup_folder(drive_service, folder_name: str = GOOGLE_DRIVE_FOLDER_NAME) -> str:
    """
    Finds the dedicated Google Drive backup folder or creates it if it doesn't exist.
    Returns the folder ID.
    """
    try:
        query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)',
            pageSize=10
        ).execute()

        files = results.get('files', [])
        if files:
            folder_id = files[0]['id']
            logger.info("Found existing Google Drive backup folder '%s' (ID: %s)", folder_name, folder_id)
            return folder_id

        # Folder does not exist, create it
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = drive_service.files().create(
            body=folder_metadata,
            fields='id'
        ).execute()

        folder_id = folder.get('id')
        logger.info("Created new Google Drive backup folder '%s' (ID: %s)", folder_name, folder_id)
        return folder_id
    except Exception as e:
        logger.error("Error retrieving/creating backup folder '%s': %s", folder_name, str(e))
        raise GoogleDriveBackupError(f"Failed to get or create backup folder: {str(e)}") from e


def upload_pdf_to_drive(drive_service, pdf_bytes: bytes, filename: str, folder_id: str) -> Dict[str, Any]:
    """
    Uploads a screenplay PDF to Google Drive in the specified folder.
    Idempotent: If a file with the same filename already exists in the folder,
    updates that file rather than creating duplicate files like 'filename (1).pdf'.
    """
    from googleapiclient.http import MediaIoBaseUpload

    media = MediaIoBaseUpload(io.BytesIO(pdf_bytes), mimetype='application/pdf', resumable=True)

    try:
        # Check if file with exact name already exists in this folder
        query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
        existing_results = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name, createdTime, size)',
            pageSize=10
        ).execute()

        existing_files = existing_results.get('files', [])

        if existing_files:
            file_id = existing_files[0]['id']
            logger.info("Daily backup file '%s' already exists (ID: %s). Updating snapshot...", filename, file_id)
            updated_file = drive_service.files().update(
                fileId=file_id,
                media_body=media,
                fields='id, name, createdTime, size'
            ).execute()
            logger.info("Google Drive backup updated successfully: %s (ID: %s)", filename, updated_file.get('id'))
            return updated_file
        else:
            file_metadata = {
                'name': filename,
                'parents': [folder_id]
            }
            created_file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, createdTime, size'
            ).execute()
            logger.info("Google Drive backup uploaded successfully: %s (ID: %s)", filename, created_file.get('id'))
            return created_file
    except Exception as e:
        logger.error("Failed to upload PDF '%s' to Google Drive: %s", filename, str(e))
        raise GoogleDriveBackupError(f"Google Drive upload failed: {str(e)}") from e


def prune_old_drive_backups(drive_service, folder_id: str, keep_count: int = BACKUP_RETENTION_COUNT) -> int:
    """
    Maintains the 30-day retention policy on Google Drive.
    Deletes older daily PDF backups in the folder beyond the newest `keep_count`.
    Must only be called AFTER a successful upload!
    """
    try:
        query = f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
        results = drive_service.files().list(
            q=query,
            spaces='drive',
            orderBy='name desc, createdTime desc',
            fields='files(id, name, createdTime)',
            pageSize=100
        ).execute()

        files = results.get('files', [])
        if len(files) <= keep_count:
            logger.info("Backup retention check: %d backups found (limit %d). No pruning needed.", len(files), keep_count)
            return 0

        files_to_delete = files[keep_count:]
        deleted_count = 0

        for f in files_to_delete:
            try:
                drive_service.files().delete(fileId=f['id']).execute()
                logger.info("Pruned old backup from Google Drive: %s (ID: %s)", f.get('name'), f.get('id'))
                deleted_count += 1
            except Exception as del_err:
                logger.warning("Could not delete old backup %s (ID: %s): %s", f.get('name'), f.get('id'), str(del_err))

        logger.info("Old backup cleanup completed: %d files pruned.", deleted_count)
        return deleted_count
    except Exception as e:
        logger.error("Error during backup pruning: %s", str(e))
        return 0


def save_local_backup(pdf_bytes: bytes, filename: str) -> str:
    """
    Saves the generated PDF to the local filesystem backup storage (media/backups/).
    Used as a fallback when Google Drive is unavailable or for local audit.
    """
    backup_dir = Path(settings.MEDIA_ROOT) / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    file_path = backup_dir / filename
    with open(file_path, 'wb') as f:
        f.write(pdf_bytes)
    logger.info("Saved local backup copy to %s (%d bytes)", file_path, len(pdf_bytes))
    return str(file_path)


def run_daily_screenplay_backup(
    script_id: Optional[int] = None,
    backup_date: Optional[date] = None,
    drive_service: Any = None,
    keep_count: int = BACKUP_RETENTION_COUNT
) -> Dict[str, Any]:
    """
    Executes the daily screenplay PDF backup job.
    1. Selects the script to backup.
    2. Generates the PDF using the ReportLab exporter (Notes excluded).
    3. Uploads to 'KadhaScript Backups' folder on Google Drive.
    4. Upon verified success, prunes backups older than 30 days.
    5. On failure, preserves the generated PDF locally and logs details without deleting older backups.
    """
    if backup_date is None:
        backup_date = timezone.localdate()

    date_str = backup_date.strftime('%Y-%m-%d')
    logger.info("==================================================")
    logger.info("Daily Screenplay Backup started for date: %s", date_str)

    # 1. Resolve Script
    if script_id:
        try:
            script = Script.objects.get(id=script_id)
        except Script.DoesNotExist:
            err = f"Script with ID {script_id} not found."
            logger.error(err)
            return {'success': False, 'error': err, 'date': date_str}

        if script.is_deleted:
            err = f"Cannot back up trashed screenplay '{script.title}' (ID: {script.id})."
            logger.error(err)
            return {'success': False, 'error': err, 'date': date_str}
    else:
        script = Script.objects.filter(is_deleted=False).order_by('-updated_at').first()
        if not script:
            err = "No active screenplay scripts found in the database to backup."
            logger.warning(err)
            return {'success': False, 'error': err, 'date': date_str}

    filename = f"KadhaScript_{date_str}.pdf"
    logger.info("Backing up script '%s' (ID: %d) as '%s'", script.title, script.id, filename)

    # 2. Generate PDF via standard exporter
    try:
        pdf_bytes = generate_screenplay_pdf(script, include_notes=False)
        logger.info("PDF generated successfully (%d bytes)", len(pdf_bytes))
    except Exception as e:
        err = f"Failed to generate screenplay PDF: {str(e)}"
        logger.error(err, exc_info=True)
        return {'success': False, 'error': err, 'date': date_str}

    # Save local copy
    local_path = None
    try:
        local_path = save_local_backup(pdf_bytes, filename)
    except Exception as e:
        logger.warning("Could not save local backup copy: %s", str(e))

    # 3. Google Drive Upload
    try:
        if drive_service is None:
            drive_service = get_gdrive_service()

        folder_id = get_or_create_backup_folder(drive_service, GOOGLE_DRIVE_FOLDER_NAME)
        uploaded_file = upload_pdf_to_drive(drive_service, pdf_bytes, filename, folder_id)

        # 4. Prune older backups ONLY after upload succeeds
        pruned_count = prune_old_drive_backups(drive_service, folder_id, keep_count=keep_count)

        logger.info("Daily screenplay backup finished successfully.")
        logger.info("==================================================")
        return {
            'success': True,
            'filename': filename,
            'date': date_str,
            'script_id': script.id,
            'script_title': script.title,
            'pdf_size': len(pdf_bytes),
            'drive_file_id': uploaded_file.get('id'),
            'local_path': local_path,
            'pruned_count': pruned_count,
            'error': None
        }

    except Exception as e:
        logger.error("Google Drive backup failed: %s", str(e), exc_info=True)
        # Preserve local file, do not delete older backups
        return {
            'success': False,
            'filename': filename,
            'date': date_str,
            'script_id': script.id,
            'script_title': script.title,
            'pdf_size': len(pdf_bytes),
            'drive_file_id': None,
            'local_path': local_path,
            'pruned_count': 0,
            'error': str(e)
        }
