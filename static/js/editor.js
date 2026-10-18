/**
 * KadhaScript Screenplay Editor Engine
 * Dedicated writing experience for Malayalam screenwriters.
 * Mobile-first responsive UX, hierarchical scenes & sub-scenes, race-condition-free save architecture.
 */

class KadhaEditor {
    constructor(config) {
        this.scriptId = config.scriptId;
        this.currentSceneId = config.currentSceneId;
        this.csrfToken = config.csrfToken;
        this.characters = config.characters || [];
        
        // DOM Elements
        this.pageContainer = document.getElementById('screenplayPage');
        this.saveBadge = document.getElementById('saveStatusBadge');
        this.scenesList = document.getElementById('scenesList');
        this.offcanvasScenesList = document.getElementById('offcanvasScenesList');
        this.offcanvasEl = document.getElementById('scenesOffcanvas');
        this.bsOffcanvas = this.offcanvasEl ? new bootstrap.Offcanvas(this.offcanvasEl) : null;
        
        // Top Scene Selector Display
        this.currentSelectorBadge = document.getElementById('currentSceneSelectorBadge');
        this.currentSelectorHeading = document.getElementById('currentSceneSelectorHeading');

        // Stats Elements
        this.wordCountEl = document.getElementById('statWordCount');
        this.charCountEl = document.getElementById('statCharCount');
        this.pageCountEl = document.getElementById('statPageCount');
        this.sceneCountEl = document.getElementById('statSceneCount');
        this.sidebarSceneCountEl = document.getElementById('sidebarSceneCount');
        this.offcanvasSceneCountEl = document.getElementById('offcanvasSceneCount');
        this.sidebarSceneHeadingTextEl = document.getElementById('sidebarSceneHeadingText');
        this.offcanvasSceneHeadingTextEl = document.getElementById('offcanvasSceneHeadingText');
        this.currentTypeEl = document.getElementById('statCurrentType');

        // Modals
        this.insertModalEl = document.getElementById('editorInsertModal');
        this.bsInsertModal = this.insertModalEl ? new bootstrap.Modal(this.insertModalEl) : null;
        this.subSceneModalEl = document.getElementById('editorSubSceneModal');
        this.bsSubSceneModal = this.subSceneModalEl ? new bootstrap.Modal(this.subSceneModalEl) : null;
        this.deleteModalEl = document.getElementById('editorDeleteModal');
        this.bsDeleteModal = this.deleteModalEl ? new bootstrap.Modal(this.deleteModalEl) : null;
        this.renameModalEl = document.getElementById('editorRenameModal');
        this.bsRenameModal = this.renameModalEl ? new bootstrap.Modal(this.renameModalEl) : null;
        this.promoteModalEl = document.getElementById('editorPromoteModal');
        this.bsPromoteModal = this.promoteModalEl ? new bootstrap.Modal(this.promoteModalEl) : null;
        this.sceneSelectModalEl = document.getElementById('editorSceneSelectModal');
        this.bsSceneSelectModal = this.sceneSelectModalEl ? new bootstrap.Modal(this.sceneSelectModalEl) : null;
        this.trashModalEl = document.getElementById('sceneTrashModal');
        this.bsTrashModal = this.trashModalEl ? new bootstrap.Modal(this.trashModalEl) : null;
        this.pendingDeleteSceneId = null;
        this.sceneSelectMode = null;
        this.isCreatingScene = false;
        this.isRestoringScene = false;

        // State Flags & Save Queue
        this.isDirty = false;
        this.isSaving = false;
        this.saveTimeout = null;
        this.activeSavePromise = null;
        this.needsQueuedSave = false;
        this.changeVersion = 0;
        this.activeElementBlock = null;
        this.scenesTree = [];
        this.currentSceneIsSub = false;

        // Navigation Coordination & Scene Loading
        this.loadRequestId = 0;
        this.isSwitchingScene = false;
        this.activeSwitchPromise = null;
        this.pendingSwitchSceneId = null;

        // Autocomplete
        this.autocompleteDropdown = document.getElementById('characterAutocomplete');
        this.autocompleteIndex = -1;

        // Editor Mode State: default is 'read'
        this.editorMode = 'read';
        this.readModeActiveSceneId = Number(config.currentSceneId);
        this._isEnteringEditMode = false;
        this.editorRoot = document.getElementById('screenplayEditor');
        this.readModeContainer = document.getElementById('readModeContainer');
        this.btnEditFab = document.getElementById('btnEnterEditMode') || document.getElementById('readModeEditButton');
        this.btnDoneFab = document.getElementById('btnExitEditMode') || document.getElementById('readModeDoneButton');
        this.readModeObserver = null;
        this.suggestionPopup = document.getElementById('elementSuggestionPopup');
        this.activeSuggestionBlock = null;
        this.activeSuggestionIndex = -1;
        this.lastCopiedPayload = null;
        this.undoStacks = {};
        this.redoStacks = {};
        this.maxHistoryStack = 50;
        this.textEditTimer = null;
        this.textEditTimerSceneId = null;
        this.isComposing = false;
        this.lastCapturedSnapshot = null;

        window.editor = this;
        window.editorInstance = this;
        this.init();
    }

    init() {
        this.bindSceneItemEvents(this.scenesList);
        this.bindSceneItemEvents(this.offcanvasScenesList);
        this.loadCurrentScene();
        this.bindGlobalEvents();
        this.bindToolbarButtons();
        this.bindSceneModals();
        this.bindSceneSelectEvents();
        this.bindSceneSearch();
        this.bindFindReplace();
        this.bindNetworkEvents();
        this.bindSwipeNavigation();
        this.bindModeToggleEvents();
        this.setEditorMode('read', false);
        this.setupReadModeScrollObserver();
        this.bindSuggestionPopupEvents();
        this.bindClipboardEvents();
        this.bindSceneTrashEvents();
        this.fetchSceneTrashCount();
    }

    // CSRF & Headers helper
    getHeaders() {
        return {
            'Content-Type': 'application/json',
            'X-CSRFToken': this.csrfToken,
        };
    }

    // ----------------------------------------------------
    // SCENE LOADING & RENDERING
    // ----------------------------------------------------
    async loadCurrentScene() {
        const requestId = ++this.loadRequestId;
        const requestedSceneId = this.currentSceneId;
        try {
            this.setSaveStatus('saving', 'Loading scene...');
            const res = await fetch(`/scripts/api/${this.scriptId}/scenes/${requestedSceneId}/`);
            if (requestId !== this.loadRequestId) {
                return;
            }
            if (!res.ok) throw new Error(`Failed to load scene (HTTP ${res.status})`);
            const data = await res.json();
            if (requestId !== this.loadRequestId) {
                return;
            }
            if (Number(data?.scene?.id) !== Number(this.currentSceneId)) {
                return;
            }
            
            this.characters = data.characters || this.characters;
            this.scenesTree = data.scenes_tree || [];
            this.currentSceneIsSub = Boolean(data.scene.is_sub_scene);
            this.currentSceneIsSequence = Boolean(data.scene.is_sequence);
            this.currentSceneSequenceType = data.scene.sequence_type || '';
            this.currentSceneHeading = data.scene.heading || '';
            this.currentMainSceneId = data.scene.parent_scene_id || data.scene.id;
            const fallbackIdent = data.scene.nav_identifier
                || data.scene.display_number
                || (data.scene.scene_number ? ('Scene ' + data.scene.scene_number + (data.scene.is_sub_scene ? '.A' : '')) : (data.scene.is_sub_scene ? 'Sub-Scene' : 'Scene'));
            this.currentSceneIdentifier = data.scene.scene_identifier || fallbackIdent;
            this.currentSceneTransition = (data.scene.transition || 'CUT TO').trim();
            const cleanHeading = (data.scene.clean_heading || data.scene.heading || '').replace(/^(?:Scene\s+\d+(?:\.[A-Za-z]+)?\s*[:—\-]\s*)+/i, '').trim();
            this.currentFullHeading = data.scene.full_display_heading || `${this.currentSceneIdentifier} : ${cleanHeading}`;
            
            // Update scene selector labels
            if (this.currentSelectorBadge) {
                this.currentSelectorBadge.innerText = this.currentFullHeading;
            }
            if (this.currentSelectorHeading) {
                this.currentSelectorHeading.innerText = '';
            }

            this.renderSceneElements(data.scene, data.elements);
            this.updateReadModeScene(data.scene.id, {
                heading: data.scene.heading,
                elements: data.elements,
                transition: data.scene.transition
            });
            this.renderScenesTree(this.scenesTree);
            this.updateSceneContextControls(data.scene);
            this.updateStats(data.script_stats);
            if (this.pageContainer) {
                this.pageContainer.dataset.loadedSceneId = String(data.scene.id);
            }
            this.setSaveStatus('saved', 'Saved ✓');
            this.isDirty = false;
            this.needsQueuedSave = false;
            this.changeVersion = 0;
            this.initSceneHistory(data.scene.id);
        } catch (err) {
            if (requestId !== this.loadRequestId) {
                return;
            }
            console.error('Error loading scene:', err);
            this.setSaveStatus('error', 'Error loading scene');
            if (this.pageContainer) {
                this.pageContainer.dataset.loadedSceneId = '';
                this.pageContainer.innerHTML = '<div class="alert alert-danger my-4">Failed to load scene. Please check your connection and click to retry.</div>';
            }
        }
    }

    updateSceneContextControls(scene) {
        if (!scene) return;
        const isSub = Boolean(scene.is_sub_scene);
        this.currentSceneIsSub = isSub;

        // 1. Toolbar Scene Dropdown
        const btnTbInsertBefore = document.getElementById('btnToolbarInsertBefore');
        if (btnTbInsertBefore) {
            btnTbInsertBefore.innerHTML = `<i class="bi bi-arrow-up-circle me-2 text-primary"></i>${isSub ? 'Insert Sub Scene Before' : 'Insert Scene Before'}`;
        }
        const btnTbInsertAfter = document.getElementById('btnToolbarInsertAfter');
        if (btnTbInsertAfter) {
            btnTbInsertAfter.innerHTML = `<i class="bi bi-arrow-down-circle me-2 text-success"></i>${isSub ? 'Insert Sub Scene After' : 'Insert Scene After'}`;
        }
        const tbSubItem = document.getElementById('toolbarAddSubSceneItem') || (document.getElementById('btnToolbarAddSubScene') ? document.getElementById('btnToolbarAddSubScene').closest('li') : null);
        if (tbSubItem) {
            tbSubItem.style.display = isSub ? 'none' : 'block';
        }

        // 2. Sidebar Top Dropdown
        const btnSbInsert = document.getElementById('btnSidebarInsertScene');
        if (btnSbInsert) {
            btnSbInsert.innerHTML = `<i class="bi bi-plus-circle me-2 text-primary"></i>${isSub ? 'Insert Sub Scene' : 'Insert Scene'}`;
        }
        const sbSubItem = document.getElementById('sidebarAddSubSceneItem') || (document.getElementById('btnSidebarSubScene') ? document.getElementById('btnSidebarSubScene').closest('li') : null);
        if (sbSubItem) {
            sbSubItem.style.display = isSub ? 'none' : 'block';
        }

        // 3. Mobile Offcanvas Header Buttons
        const btnOcSub = document.getElementById('btnOffcanvasSubScene');
        if (btnOcSub) {
            btnOcSub.style.display = isSub ? 'none' : 'inline-flex';
        }
        const btnOcInsert = document.getElementById('btnOffcanvasInsertScene');
        if (btnOcInsert) {
            btnOcInsert.title = isSub ? 'Insert Sub Scene' : 'Insert Scene';
        }
    }

    parseHeading(rawHeading) {
        let text = (rawHeading || '').replace(/^(?:Scene\s+\d+(?:\.[A-Za-z]+)?\s*[:—\-]\s*)+/i, '').trim();
        if (!text) {
            return { intext: 'INT.', location: '', time: 'DAY' };
        }

        // Standard regex matching INT. / EXT. with optional time
        const regex = /^\s*(INT\.?|EXT\.?|INTERIOR|EXTERIOR)\s+(.+?)(?:\s*[-—–]\s*(DAY|NIGHT|DUSK|DAWN|CONTINUOUS|LATER|MOMENTS LATER))?\s*$/i;
        const match = text.match(regex);

        if (match) {
            const intextPrefix = match[1].toUpperCase().startsWith('EXT') ? 'EXT.' : 'INT.';
            const locationPart = (match[2] || '').trim();
            let rawTime = (match[3] || 'DAY').toUpperCase();
            if (!['DAY', 'NIGHT', 'DUSK', 'DAWN'].includes(rawTime)) {
                rawTime = 'DAY';
            }
            return {
                intext: intextPrefix,
                location: locationPart,
                time: rawTime
            };
        }

        // Fallback: If not starting with standard INT./EXT., safely preserve entire text in location
        return {
            intext: 'INT.',
            location: text,
            time: 'DAY'
        };
    }

    buildHeading(intext = 'INT.', location = '', time = 'DAY') {
        const cleanIntext = (intext && intext.toUpperCase().startsWith('EXT')) ? 'EXT.' : 'INT.';
        const cleanLoc = (location || '').trim();
        let cleanTime = (time || 'DAY').trim().toUpperCase();
        if (!['DAY', 'NIGHT', 'DUSK', 'DAWN'].includes(cleanTime)) {
            cleanTime = 'DAY';
        }
        if (!cleanLoc) {
            return '';
        }
        return `${cleanIntext} ${cleanLoc} - ${cleanTime}`;
    }

    renderSceneElements(scene, elements) {
        if (this.pageContainer) {
            this.pageContainer.dataset.loadedSceneId = String(scene.id);
            this.pageContainer.innerHTML = '';
        }

        const allElements = elements || [];
        const contentElements = allElements.filter(e => e.element_type !== 'note');
        const noteElements = allElements.filter(e => e.element_type === 'note');

        if (contentElements.length === 0) {
            if (scene.is_sequence || (scene.heading && (scene.heading.startsWith('SONG') || scene.heading.startsWith('MONTAGE')))) {
                this.createElementBlock('shot', scene.heading || 'SONG BEGINS');
                this.createElementBlock('shot', '1. INT. LOCATION - DAY');
                this.createElementBlock('action', '');
            } else {
                this.createElementBlock('scene_heading', scene.heading || 'INT. LOCATION - DAY');
                this.createElementBlock('action', '');
            }
        } else {
            contentElements.forEach(elem => {
                this.createElementBlock(elem.element_type, elem.content);
            });
        }

        // Render any Notes
        noteElements.forEach(elem => {
            this.createElementBlock(elem.element_type, elem.content);
        });

        this.updateSequenceToolbarState();
        // Edit Mode entry does not automatically steal focus; user explicitly clicks to focus
    }

    formatParenthetical(text) {
        if (!text) return '';
        let trimmed = text.trim();
        if (!trimmed) return '';

        // Strip any existing outer parentheses or square brackets (including multiples or unmatched)
        while (
            ((trimmed.startsWith('(') && trimmed.endsWith(')')) || (trimmed.startsWith('[') && trimmed.endsWith(']')))
            && trimmed.length >= 2
        ) {
            trimmed = trimmed.slice(1, -1).trim();
        }
        if (trimmed.startsWith('(') || trimmed.startsWith('[')) {
            trimmed = trimmed.slice(1).trim();
        }
        if (trimmed.endsWith(')') || trimmed.endsWith(']')) {
            trimmed = trimmed.slice(0, -1).trim();
        }

        if (!trimmed) return '';
        return `(${trimmed})`;
    }

    createElementBlock(type = 'action', content = '', insertAfter = null) {
        const block = document.createElement('div');
        block.className = 'script-element-block';
        block.dataset.type = type;

        const tag = document.createElement('span');
        tag.className = 'element-type-tag';
        tag.innerText = this.formatTypeLabel(type);
        block.appendChild(tag);

        if (type === 'scene_heading') {
            const parsed = this.parseHeading(content);
            const lineWrapper = document.createElement('div');
            lineWrapper.className = 'scene-heading-line';

            const prefix = document.createElement('span');
            prefix.className = 'scene-prefix-label font-screenplay user-select-none';
            const currentSceneMeta = (this.scenesTree || []).find(s => Number(s.id) === Number(this.currentSceneId));
            const fallbackIdent = (currentSceneMeta && (currentSceneMeta.scene_identifier || currentSceneMeta.nav_identifier || currentSceneMeta.display_number))
                || (this.currentSceneIsSub ? 'Sub-Scene' : 'Scene');
            prefix.innerText = (this.currentSceneIdentifier || fallbackIdent) + ' :';
            lineWrapper.appendChild(prefix);

            const builder = document.createElement('div');
            builder.className = 'scene-heading-builder';
            builder.contentEditable = 'false';

            // 1. Interior/Exterior dropdown
            const intextSelect = document.createElement('select');
            intextSelect.className = 'form-select form-select-sm heading-intext-select font-screenplay user-select-none';
            intextSelect.title = 'Interior / Exterior';
            intextSelect.innerHTML = `
                <option value="INT." ${parsed.intext === 'INT.' ? 'selected' : ''}>Interior</option>
                <option value="EXT." ${parsed.intext === 'EXT.' ? 'selected' : ''}>Exterior</option>
            `;

            // 2. Editable location field
            const locationInput = document.createElement('input');
            locationInput.type = 'text';
            locationInput.className = 'form-control form-control-sm heading-location-input font-screenplay font-malayalam';
            locationInput.placeholder = 'Enter location...';
            locationInput.value = parsed.location || '';
            locationInput.spellcheck = false;
            locationInput.autocomplete = 'off';

            // 3. Time-of-day dropdown
            const timeSelect = document.createElement('select');
            timeSelect.className = 'form-select form-select-sm heading-time-select font-screenplay user-select-none';
            timeSelect.title = 'Time of Day';
            timeSelect.innerHTML = `
                <option value="DAY" ${parsed.time === 'DAY' ? 'selected' : ''}>Day</option>
                <option value="NIGHT" ${parsed.time === 'NIGHT' ? 'selected' : ''}>Night</option>
                <option value="DUSK" ${parsed.time === 'DUSK' ? 'selected' : ''}>Dusk</option>
                <option value="DAWN" ${parsed.time === 'DAWN' ? 'selected' : ''}>Dawn</option>
            `;

            builder.appendChild(intextSelect);
            builder.appendChild(locationInput);
            builder.appendChild(timeSelect);
            lineWrapper.appendChild(builder);

            // Hidden element-content to preserve compatibility with element iteration and serializer
            const editable = document.createElement('div');
            editable.className = 'element-content font-screenplay font-malayalam d-none';
            editable.contentEditable = 'true';
            const initialHeading = this.buildHeading(parsed.intext, parsed.location, parsed.time);
            editable.innerText = initialHeading || `${parsed.intext} ${parsed.location || 'LOCATION'} - ${parsed.time}`;
            lineWrapper.appendChild(editable);

            block.appendChild(lineWrapper);

            // Event handlers for the 3 controls
            const syncHeading = () => {
                const locVal = locationInput.value.trim();
                const built = this.buildHeading(intextSelect.value, locVal, timeSelect.value);
                editable.innerText = built || `${intextSelect.value} ${locVal || 'LOCATION'} - ${timeSelect.value}`;

                if (locVal === '') {
                    locationInput.classList.add('is-invalid');
                } else {
                    locationInput.classList.remove('is-invalid');
                }

                const currentSceneMeta = (this.scenesTree || []).find(s => Number(s.id) === Number(this.currentSceneId));
                const currentIdent = this.currentSceneIdentifier
                    || (currentSceneMeta && (currentSceneMeta.scene_identifier || currentSceneMeta.nav_identifier || currentSceneMeta.display_number))
                    || (this.currentSceneIsSub ? 'Sub-Scene' : 'Scene');
                const fullHeading = locVal ? `${currentIdent} : ${built}` : `${currentIdent} : UNTITLED SCENE`;

                const targetSceneId = Number(this.currentSceneId);
                const displayLoc = locVal || 'Location';
                const activeSidebarLocs = document.querySelectorAll(`.scene-item[data-id="${targetSceneId}"] .scene-nav-location`);
                activeSidebarLocs.forEach(item => {
                    item.innerText = displayLoc;
                    item.title = displayLoc;
                });
                if (this.currentSelectorBadge) {
                    this.currentSelectorBadge.innerText = fullHeading;
                }

                const treeItem = (this.scenesTree || []).find(sc => Number(sc.id) === targetSceneId);
                if (treeItem) {
                    treeItem.clean_location = locVal;
                    treeItem.clean_heading = built;
                    treeItem.heading = built;
                    treeItem.full_display_heading = fullHeading;
                }

                const activeCards = document.querySelectorAll(`.scene-item[data-id="${targetSceneId}"]`);
                activeCards.forEach(card => {
                    card.querySelectorAll('.btn-action-insert-before, .btn-action-insert-after, .btn-action-add-sub, .btn-action-delete, .btn-action-rename').forEach(btn => {
                        btn.dataset.heading = built;
                    });
                });

                this.markDirty();
                this.calculateLiveStats();
            };

            locationInput.addEventListener('input', () => {
                syncHeading();
                this.recordTextEdit();
            });
            intextSelect.addEventListener('change', () => {
                const preSnap = this.captureSnapshot();
                syncHeading();
                this.pushUndoSnapshot(preSnap);
            });
            timeSelect.addEventListener('change', () => {
                const preSnap = this.captureSnapshot();
                syncHeading();
                this.pushUndoSnapshot(preSnap);
            });

            locationInput.addEventListener('focus', () => {
                document.querySelectorAll('.script-element-block.focused').forEach(b => b.classList.remove('focused'));
                block.classList.add('focused');
                this.activeElementBlock = block;
                this.updateActiveToolbarButton('scene_heading');
                if (this.currentTypeEl) {
                    this.currentTypeEl.innerText = 'Heading';
                }
            });

            locationInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    let nextBlock = block.nextElementSibling;
                    if (!nextBlock || !nextBlock.classList.contains('script-element-block')) {
                        nextBlock = this.createElementBlock('action', '', block);
                    }
                    const nextEditable = nextBlock.querySelector('.element-content:not(.d-none)') || nextBlock.querySelector('.element-content');
                    if (nextEditable) {
                        nextEditable.focus();
                        this.setCursorToStart(nextEditable);
                    }
                }
            });

            this.bindElementEvents(block, editable);
        } else if (type === 'transition') {
            const wrapper = document.createElement('div');
            wrapper.className = 'transition-element-wrapper';

            const editable = document.createElement('div');
            editable.className = 'element-content font-screenplay font-malayalam';
            editable.contentEditable = 'true';
            editable.spellcheck = false;
            editable.dataset.placeholder = this.getPlaceholderForType(type);
            editable.innerText = content ? content.trim() : 'CUT TO:';

            const pickerDropdown = document.createElement('div');
            pickerDropdown.className = 'transition-picker-dropdown dropdown';
            pickerDropdown.contentEditable = 'false';

            const toggleBtn = document.createElement('button');
            toggleBtn.className = 'btn btn-sm transition-dropdown-btn dropdown-toggle';
            toggleBtn.type = 'button';
            toggleBtn.dataset.bsToggle = 'dropdown';
            toggleBtn.dataset.bsPopperConfig = '{"strategy":"fixed"}';
            toggleBtn.title = 'Select transition';
            toggleBtn.tabIndex = -1;
            toggleBtn.innerHTML = '<i class="bi bi-chevron-down"></i>';

            const menu = document.createElement('ul');
            menu.className = 'dropdown-menu dropdown-menu-end shadow-sm small transition-options-menu';

            const standardTransitions = [
                'CUT TO:',
                'FADE IN:',
                'FADE OUT:',
                'DISSOLVE TO:',
                'SMASH CUT TO:',
                'MATCH CUT TO:',
                'INTERCUT',
                'CUT BACK TO:',
            ];

            standardTransitions.forEach(trans => {
                const li = document.createElement('li');
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'dropdown-item transition-opt-item';
                btn.innerText = trans;
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const preSnap = this.captureSnapshot();
                    editable.innerText = trans;
                    this.pushUndoSnapshot(preSnap);
                    this.markDirty();
                    this.calculateLiveStats();
                    editable.focus();
                    this.setCursorToEnd(editable);
                });
                li.appendChild(btn);
                menu.appendChild(li);
            });

            const divider = document.createElement('li');
            divider.innerHTML = '<hr class="dropdown-divider">';
            menu.appendChild(divider);

            const customLi = document.createElement('li');
            const customBtn = document.createElement('button');
            customBtn.type = 'button';
            customBtn.className = 'dropdown-item text-muted';
            customBtn.innerHTML = '<i class="bi bi-pencil me-1"></i> Custom Transition...';
            customBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                editable.focus();
                const range = document.createRange();
                range.selectNodeContents(editable);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
            });
            customLi.appendChild(customBtn);
            menu.appendChild(customLi);

            pickerDropdown.appendChild(toggleBtn);
            pickerDropdown.appendChild(menu);

            wrapper.appendChild(editable);
            wrapper.appendChild(pickerDropdown);
            block.appendChild(wrapper);

            this.bindElementEvents(block, editable);
        } else if (type === 'shot') {
            const trimmed = (content || '').trim();
            if (trimmed === 'SONG BEGINS' || trimmed === 'MONTAGE BEGINS') {
                block.classList.add('sequence-marker', 'sequence-marker-start');
                block.dataset.sequenceType = trimmed.startsWith('SONG') ? 'song' : 'montage';
                tag.innerText = trimmed.startsWith('SONG') ? 'Song Sequence' : 'Montage';

                const editable = document.createElement('div');
                editable.className = 'element-content font-screenplay font-malayalam';
                editable.contentEditable = 'true';
                editable.spellcheck = false;
                editable.dataset.placeholder = trimmed;
                editable.innerText = trimmed;

                block.appendChild(editable);
                this.bindElementEvents(block, editable);
            } else if (trimmed === 'SONG ENDS' || trimmed === 'MONTAGE ENDS') {
                block.classList.add('sequence-marker', 'sequence-marker-end');
                block.dataset.sequenceType = trimmed.startsWith('SONG') ? 'song' : 'montage';
                tag.innerText = 'Sequence End';

                const editable = document.createElement('div');
                editable.className = 'element-content font-screenplay font-malayalam';
                editable.contentEditable = 'true';
                editable.spellcheck = false;
                editable.dataset.placeholder = trimmed;
                editable.innerText = trimmed;

                block.appendChild(editable);
                this.bindElementEvents(block, editable);
            } else if (/^\s*(\d+)\.\s*/.test(trimmed)) {
                block.classList.add('sequence-shot-heading');
                tag.innerText = 'Sequence Shot';

                const match = trimmed.match(/^\s*(\d+)\.\s*(.*)$/);
                const num = match ? match[1] : '1';
                const sluglinePart = match ? match[2] : '';
                const parsed = this.parseHeading(sluglinePart);

                const lineWrapper = document.createElement('div');
                lineWrapper.className = 'sequence-shot-line';

                const numSpan = document.createElement('span');
                numSpan.className = 'sequence-shot-number font-screenplay user-select-none';
                numSpan.innerText = `${num}.`;
                lineWrapper.appendChild(numSpan);

                const builder = document.createElement('div');
                builder.className = 'scene-heading-builder sequence-shot-builder';
                builder.contentEditable = 'false';

                // 1. Interior/Exterior dropdown
                const intextSelect = document.createElement('select');
                intextSelect.className = 'form-select form-select-sm heading-intext-select font-screenplay user-select-none';
                intextSelect.title = 'Interior / Exterior';
                intextSelect.innerHTML = `
                    <option value="INT." ${parsed.intext === 'INT.' ? 'selected' : ''}>Interior</option>
                    <option value="EXT." ${parsed.intext === 'EXT.' ? 'selected' : ''}>Exterior</option>
                `;

                // 2. Editable location field
                const locationInput = document.createElement('input');
                locationInput.type = 'text';
                locationInput.className = 'form-control form-control-sm heading-location-input font-screenplay font-malayalam';
                locationInput.placeholder = 'Enter location...';
                locationInput.value = parsed.location || '';
                locationInput.spellcheck = false;
                locationInput.autocomplete = 'off';

                // 3. Time-of-day dropdown
                const timeSelect = document.createElement('select');
                timeSelect.className = 'form-select form-select-sm heading-time-select font-screenplay user-select-none';
                timeSelect.title = 'Time of Day';
                timeSelect.innerHTML = `
                    <option value="DAY" ${parsed.time === 'DAY' ? 'selected' : ''}>Day</option>
                    <option value="NIGHT" ${parsed.time === 'NIGHT' ? 'selected' : ''}>Night</option>
                    <option value="DUSK" ${parsed.time === 'DUSK' ? 'selected' : ''}>Dusk</option>
                    <option value="DAWN" ${parsed.time === 'DAWN' ? 'selected' : ''}>Dawn</option>
                `;

                builder.appendChild(intextSelect);
                builder.appendChild(locationInput);
                builder.appendChild(timeSelect);
                lineWrapper.appendChild(builder);

                // Hidden element-content to preserve compatibility with element iteration and serializer
                const editable = document.createElement('div');
                editable.className = 'element-content font-screenplay font-malayalam d-none';
                editable.contentEditable = 'true';
                const initialHeading = this.buildHeading(parsed.intext, parsed.location, parsed.time);
                editable.innerText = `${num}. ${initialHeading || `${parsed.intext} ${parsed.location || 'LOCATION'} - ${parsed.time}`}`;
                lineWrapper.appendChild(editable);

                block.appendChild(lineWrapper);

                const syncSequenceHeading = () => {
                    const locVal = locationInput.value.trim();
                    const built = this.buildHeading(intextSelect.value, locVal, timeSelect.value);
                    const currentNum = (numSpan.innerText || '').replace('.', '').trim() || num;
                    editable.innerText = `${currentNum}. ${built || `${intextSelect.value} ${locVal || 'LOCATION'} - ${timeSelect.value}`}`;
                    if (locVal === '') {
                        locationInput.classList.add('is-invalid');
                    } else {
                        locationInput.classList.remove('is-invalid');
                    }
                    this.markDirty();
                    this.calculateLiveStats();
                };

                locationInput.addEventListener('input', () => {
                    syncSequenceHeading();
                    this.recordTextEdit();
                });
                intextSelect.addEventListener('change', () => {
                    const preSnap = this.captureSnapshot();
                    syncSequenceHeading();
                    this.pushUndoSnapshot(preSnap);
                });
                timeSelect.addEventListener('change', () => {
                    const preSnap = this.captureSnapshot();
                    syncSequenceHeading();
                    this.pushUndoSnapshot(preSnap);
                });

                locationInput.addEventListener('focus', () => {
                    document.querySelectorAll('.script-element-block.focused').forEach(b => b.classList.remove('focused'));
                    block.classList.add('focused');
                    this.activeElementBlock = block;
                    this.updateActiveToolbarButton('shot');
                    if (this.currentTypeEl) {
                        this.currentTypeEl.innerText = 'Sequence Shot';
                    }
                    this.updateSequenceToolbarState();
                });

                locationInput.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        let nextBlock = block.nextElementSibling;
                        if (!nextBlock || !nextBlock.classList.contains('script-element-block')) {
                            nextBlock = this.createElementBlock('action', '', block);
                        }
                        const nextEditable = nextBlock.querySelector('.element-content:not(.d-none)') || nextBlock.querySelector('.element-content');
                        if (nextEditable) {
                            nextEditable.focus();
                            this.setCursorToStart(nextEditable);
                        }
                    }
                });

                this.bindElementEvents(block, editable);
            } else {
                const editable = document.createElement('div');
                editable.className = 'element-content font-screenplay font-malayalam';
                editable.contentEditable = 'true';
                editable.spellcheck = false;
                editable.dataset.placeholder = this.getPlaceholderForType(type);
                editable.innerText = content;

                block.appendChild(editable);
                this.bindElementEvents(block, editable);
            }
        } else {
            const editable = document.createElement('div');
            editable.className = 'element-content font-screenplay font-malayalam';
            editable.contentEditable = 'true';
            editable.spellcheck = false;
            editable.dataset.placeholder = this.getPlaceholderForType(type);
            editable.innerText = (type === 'parenthetical' && content) ? this.formatParenthetical(content) : content;

            block.appendChild(editable);
            this.bindElementEvents(block, editable);
        }

        if (insertAfter && insertAfter.parentNode === this.pageContainer) {
            this.pageContainer.insertBefore(block, insertAfter.nextSibling);
        } else if (type === 'note') {
            this.pageContainer.appendChild(block);
        } else {
            const firstNote = this.pageContainer.querySelector('.script-element-block[data-type="note"]');
            if (firstNote && firstNote.parentNode === this.pageContainer) {
                this.pageContainer.insertBefore(block, firstNote);
            } else {
                this.pageContainer.appendChild(block);
            }
        }

        return block;
    }

    formatTypeLabel(type) {
        const map = {
            'scene_heading': 'Heading',
            'action': 'Action',
            'character': 'Character',
            'dialogue': 'Dialogue',
            'parenthetical': 'Parenthetical',
            'transition': 'Transition',
            'shot': 'Shot',
            'note': 'Note'
        };
        return map[type] || type;
    }

    getPlaceholderForType(type) {
        const map = {
            'scene_heading': 'INT./EXT. LOCATION - DAY/NIGHT (e.g. INT. വീട് - രാത്രി)',
            'action': 'Scene description and action in Malayalam or English...',
            'character': 'CHARACTER NAME (e.g. ANU or അനു)',
            'dialogue': 'Dialogue spoken by character...',
            'parenthetical': '(beat, smiling, whispering...)',
            'transition': 'CUT TO: / FADE OUT.',
            'shot': 'CLOSE UP / ANGLE ON...',
            'note': 'Screenplay note / research / reminder...'
        };
        return map[type] || 'Write here...';
    }

    // ----------------------------------------------------
    // ELEMENT INTERACTION & KEYBOARD STANDARDS
    // ----------------------------------------------------
    bindElementEvents(block, editable) {
        // Focus tracking
        editable.addEventListener('focus', () => {
            document.querySelectorAll('.script-element-block.focused').forEach(b => b.classList.remove('focused'));
            block.classList.add('focused');
            this.activeElementBlock = block;
            this.updateActiveToolbarButton(block.dataset.type);
            if (this.currentTypeEl) {
                if (block.classList.contains('sequence-marker')) {
                    this.currentTypeEl.innerText = 'Sequence';
                } else if (block.classList.contains('sequence-shot-heading')) {
                    this.currentTypeEl.innerText = 'Sequence Shot';
                } else {
                    this.currentTypeEl.innerText = this.formatTypeLabel(block.dataset.type);
                }
            }
            this.updateSequenceToolbarState();
        });

        editable.addEventListener('blur', () => {
            if (block.dataset.type === 'parenthetical') {
                const text = editable.innerText.trim();
                if (text) {
                    const formatted = this.formatParenthetical(text);
                    if (editable.innerText !== formatted) {
                        editable.innerText = formatted;
                        this.markDirty();
                        this.calculateLiveStats();
                    }
                }
            }
        });

        // Input & Changes
        editable.addEventListener('input', () => {
            // Dismiss suggestions immediately when typing begins
            this.hideSuggestionPopup();
            this.markDirty();
            this.calculateLiveStats();

            // Sync Scene Heading with sidebar & top button in real-time
            if (block.dataset.type === 'scene_heading') {
                const rawHeading = editable.innerText.trim();
                const cleanHeading = rawHeading.replace(/^(?:Scene\s+\d+(?:\.[A-Za-z]+)?\s*[:—\-]\s*)+/i, '').trim();
                const currentSceneMeta = (this.scenesTree || []).find(s => Number(s.id) === Number(this.currentSceneId));
                const currentIdent = this.currentSceneIdentifier
                    || (currentSceneMeta && (currentSceneMeta.scene_identifier || currentSceneMeta.nav_identifier || currentSceneMeta.display_number))
                    || (this.currentSceneIsSub ? 'Sub-Scene' : 'Scene');
                const fullHeading = cleanHeading ? `${currentIdent} : ${cleanHeading}` : `${currentIdent} : UNTITLED SCENE`;
                const targetSceneId = Number(this.currentSceneId);
                const prefixStripped = cleanHeading.replace(/^(?:(?:INT\.\/EXT\.|EXT\.\/INT\.|INT\/EXT|EXT\/INT|INT\.|EXT\.|I\/E\.|INT|EXT)\s*[:\.\-\s]\s*)/i, '').trim();
                const parts = prefixStripped.split(/\s+[-–—]\s+/).map(p => p.trim()).filter(Boolean);
                const timeTokens = new Set([
                    'DAY', 'NIGHT', 'DAWN', 'DUSK', 'MORNING', 'EVENING', 'AFTERNOON',
                    'SUNSET', 'SUNRISE', 'CONTINUOUS', 'LATER', 'SAME TIME', 'MOMENTS LATER',
                    'SAME', 'FLASHBACK', 'MAGIC HOUR', 'EARLY MORNING', 'LATE NIGHT',
                    'RAIN', 'STORM', 'SNOW', 'FOG', 'WIND',
                    'പകൽ', 'രാത്രി', 'പ്രഭാതം', 'സന്ധ്യ', 'തുടർച്ച', 'വൈകുന്നേരം', 'ഉച്ച', 'മഴ'
                ]);
                let displayLoc = cleanHeading;
                if (parts.length > 1 && timeTokens.has(parts[parts.length - 1].toUpperCase())) {
                    displayLoc = parts.slice(0, -1).join(' - ');
                } else if (parts.length > 0) {
                    displayLoc = parts.join(' - ');
                }
                displayLoc = displayLoc || cleanHeading || 'Location';

                const activeSidebarLocs = document.querySelectorAll(`.scene-item[data-id="${targetSceneId}"] .scene-nav-location`);
                activeSidebarLocs.forEach(item => {
                    item.innerText = displayLoc;
                    item.title = displayLoc;
                });
                if (this.currentSelectorBadge) {
                    this.currentSelectorBadge.innerText = fullHeading;
                }

                const treeItem = (this.scenesTree || []).find(sc => Number(sc.id) === targetSceneId);
                if (treeItem) {
                    treeItem.clean_location = displayLoc;
                    treeItem.clean_heading = cleanHeading;
                    treeItem.heading = cleanHeading;
                }
            }

            // Character autocomplete trigger
            if (block.dataset.type === 'character') {
                this.handleCharacterInput(editable);
            } else {
                this.hideAutocomplete();
            }

            this.recordTextEdit();
        });

        editable.addEventListener('compositionstart', () => {
            this.isComposing = true;
        });

        editable.addEventListener('compositionend', () => {
            this.isComposing = false;
            this.recordTextEdit();
        });

        // Keydown handling: Enter, Tab, Backspace, Arrows
        editable.addEventListener('keydown', (e) => {
            // Suggestion popup keyboard navigation
            if (this.suggestionPopup && this.suggestionPopup.style.display === 'inline-flex') {
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    this.navigateSuggestions(1);
                    return;
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    this.navigateSuggestions(-1);
                    return;
                } else if (e.key === 'Enter') {
                    const chips = this.suggestionPopup.querySelectorAll('.suggestion-chip');
                    if (this.activeSuggestionIndex >= 0 && chips[this.activeSuggestionIndex]) {
                        e.preventDefault();
                        const sugType = chips[this.activeSuggestionIndex].dataset.suggestion;
                        this.applySuggestion(sugType, this.activeSuggestionBlock || block);
                        return;
                    }
                } else if (e.key === 'Escape') {
                    this.hideSuggestionPopup();
                    return;
                }
            }

            // Autocomplete navigation
            if (this.autocompleteDropdown && this.autocompleteDropdown.style.display === 'block') {
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    this.navigateAutocomplete(1);
                    return;
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    this.navigateAutocomplete(-1);
                    return;
                } else if (e.key === 'Enter' || e.key === 'Tab') {
                    e.preventDefault();
                    this.selectAutocompleteItem();
                    return;
                } else if (e.key === 'Escape') {
                    this.hideAutocomplete();
                    return;
                }
            }

            // Enter key handling (Notes support multiline notepad behavior)
            if (e.key === 'Enter') {
                if (block.dataset.type === 'note') {
                    e.preventDefault();
                    this.handleNoteEnter(block, editable);
                    return;
                }
                if (!e.shiftKey) {
                    e.preventDefault();
                    this.handleEnterKey(block, editable);
                    return;
                }
            }

            // Tab key handling (Notes insert 2 spaces indent instead of cycling screenplay types)
            if (e.key === 'Tab') {
                e.preventDefault();
                if (block.dataset.type === 'note') {
                    if (!e.shiftKey) {
                        document.execCommand('insertText', false, '  ');
                        this.markDirty();
                        this.calculateLiveStats();
                    }
                    return;
                }
                this.cycleElementType(block, e.shiftKey ? -1 : 1);
                return;
            }

            // Backspace on empty block
            if (e.key === 'Backspace' && editable.innerText.trim() === '') {
                const prevBlock = block.previousElementSibling;
                if (prevBlock && prevBlock.classList.contains('script-element-block')) {
                    e.preventDefault();
                    const preSnap = this.captureSnapshot();
                    block.remove();
                    this.renumberSequenceShots();
                    this.updateSequenceToolbarState();
                    this.pushUndoSnapshot(preSnap);
                    this.markDirty();
                    this.calculateLiveStats();
                    const prevEditable = prevBlock.querySelector('.element-content:not(.d-none)') || prevBlock.querySelector('.element-content');
                    if (prevEditable) {
                        prevEditable.focus();
                        this.setCursorToEnd(prevEditable);
                    }
                }
                return;
            }

            // Arrow Up / Down navigation between blocks (accounts for multiline cursor position)
            if (e.key === 'ArrowUp') {
                const sel = window.getSelection();
                if (sel && sel.rangeCount > 0) {
                    const range = sel.getRangeAt(0);
                    let isAtStart = false;
                    try {
                        const preRange = document.createRange();
                        preRange.setStart(editable, 0);
                        preRange.setEnd(range.startContainer, range.startOffset);
                        isAtStart = (preRange.toString().length === 0);
                    } catch (err) {
                        isAtStart = (sel.anchorOffset === 0);
                    }
                    if (isAtStart) {
                        const prevBlock = block.previousElementSibling;
                        if (prevBlock && prevBlock.classList.contains('script-element-block')) {
                            e.preventDefault();
                            const prevEditable = prevBlock.querySelector('.element-content:not(.d-none)') || prevBlock.querySelector('.element-content');
                            if (prevEditable) {
                                prevEditable.focus();
                                this.setCursorToEnd(prevEditable);
                            }
                        }
                    }
                }
            } else if (e.key === 'ArrowDown') {
                const sel = window.getSelection();
                if (sel && sel.rangeCount > 0) {
                    const range = sel.getRangeAt(0);
                    let isAtEnd = false;
                    try {
                        const postRange = document.createRange();
                        postRange.setStart(range.endContainer, range.endOffset);
                        postRange.setEnd(editable, editable.childNodes.length);
                        isAtEnd = (postRange.toString().length === 0);
                    } catch (err) {
                        isAtEnd = (sel.anchorOffset >= editable.innerText.length);
                    }
                    if (isAtEnd) {
                        const nextBlock = block.nextElementSibling;
                        if (nextBlock && nextBlock.classList.contains('script-element-block')) {
                            e.preventDefault();
                            const nextEditable = nextBlock.querySelector('.element-content:not(.d-none)') || nextBlock.querySelector('.element-content');
                            if (nextEditable) {
                                nextEditable.focus();
                                this.setCursorToStart(nextEditable);
                            }
                        }
                    }
                }
            }
        });
    }

    // ----------------------------------------------------
    // NOTES NOTEPAD BEHAVIOR (Batch 2, Step 2)
    // ----------------------------------------------------
    handleNoteEnter(block, editable) {
        const sel = window.getSelection();
        if (!sel || sel.rangeCount === 0) {
            document.execCommand('insertLineBreak');
            this.markDirty();
            this.calculateLiveStats();
            return;
        }

        const range = sel.getRangeAt(0);

        // Find the line container element within editable
        let lineEl = range.startContainer;
        while (lineEl && lineEl !== editable && lineEl.parentElement !== editable) {
            lineEl = lineEl.parentElement;
        }
        if (lineEl === editable) {
            lineEl = range.startContainer;
        }

        // Get text before and after cursor in this line element
        let lineBefore = '';
        let lineAfter = '';
        try {
            const preRange = document.createRange();
            preRange.setStart(lineEl, 0);
            preRange.setEnd(range.startContainer, range.startOffset);
            lineBefore = preRange.toString();

            const postRange = document.createRange();
            postRange.setStart(range.endContainer, range.endOffset);
            const endLen = (lineEl.nodeType === Node.TEXT_NODE) ? lineEl.length : lineEl.childNodes.length;
            postRange.setEnd(lineEl, endLen);
            lineAfter = postRange.toString();
        } catch (err) {
            lineBefore = '';
            lineAfter = '';
        }

        const isAtEndOfLine = (lineAfter.trim() === '');

        // 1. Empty list item: stop list continuation by clearing marker
        const emptyBullet = lineBefore.match(/^(\s*[-•*]\s*)$/);
        const emptyNumber = lineBefore.match(/^(\s*\d+\.\s*)$/);

        if ((emptyBullet || emptyNumber) && isAtEndOfLine) {
            if (lineEl && lineEl !== editable && lineEl.parentElement === editable) {
                lineEl.innerHTML = '<br>';
                const newRange = document.createRange();
                newRange.setStart(lineEl, 0);
                newRange.collapse(true);
                sel.removeAllRanges();
                sel.addRange(newRange);
            } else {
                editable.innerHTML = '<br>';
                const newRange = document.createRange();
                newRange.setStart(editable, 0);
                newRange.collapse(true);
                sel.removeAllRanges();
                sel.addRange(newRange);
            }
            this.markDirty();
            this.calculateLiveStats();
            return;
        }

        // 2. Cursor at end of list item: continue list
        if (isAtEndOfLine) {
            const bulletMatch = lineBefore.match(/^(\s*)([-•*])\s+(.+)$/);
            const numberMatch = lineBefore.match(/^(\s*)(\d+)\.\s+(.+)$/);

            if (bulletMatch) {
                const indent = bulletMatch[1];
                const marker = bulletMatch[2];
                document.execCommand('insertText', false, '\n' + indent + marker + ' ');
                this.markDirty();
                this.calculateLiveStats();
                return;
            }

            if (numberMatch) {
                const indent = numberMatch[1];
                const currentNum = parseInt(numberMatch[2], 10);
                const nextNum = currentNum + 1;
                document.execCommand('insertText', false, '\n' + indent + nextNum + '. ');
                this.markDirty();
                this.calculateLiveStats();
                return;
            }
        }

        // 3. Ordinary line break
        document.execCommand('insertLineBreak');
        this.markDirty();
        this.calculateLiveStats();
    }

    handleEnterKey(block, editable) {
        const currentType = block.dataset.type;
        const currentText = editable.innerText.trim();

        if (currentType === 'note') {
            this.handleNoteEnter(block, editable);
            return;
        }

        const preSnap = this.captureSnapshot();

        // ----------------------------------------------------
        // ACTION PARAGRAPH SPLITTING (Batch 2, Step 1)
        // ----------------------------------------------------
        if (currentType === 'action') {
            const sel = window.getSelection();
            let leftText = '';
            let rightText = '';
            let hasSelectionRange = false;
            let isCollapsed = true;

            if (sel && sel.rangeCount > 0) {
                const range = sel.getRangeAt(0);
                if (editable.contains(range.startContainer) && editable.contains(range.endContainer)) {
                    hasSelectionRange = true;
                    isCollapsed = range.collapsed;

                    try {
                        const preRange = document.createRange();
                        preRange.setStart(editable, 0);
                        preRange.setEnd(range.startContainer, range.startOffset);
                        leftText = preRange.toString();

                        const postRange = document.createRange();
                        postRange.setStart(range.endContainer, range.endOffset);
                        postRange.setEnd(editable, editable.childNodes.length);
                        rightText = postRange.toString();
                    } catch (err) {
                        hasSelectionRange = false;
                    }
                }
            }

            if (!hasSelectionRange) {
                leftText = editable.innerText;
                rightText = '';
                isCollapsed = true;
            }

            const cleanLeft = leftText.trimEnd();
            const cleanRight = rightText.trimStart();

            // Case B: Cursor at the beginning with no text selection
            if (isCollapsed && cleanLeft === '' && cleanRight !== '') {
                const emptyBlock = this.createElementBlock('action', '');
                this.pageContainer.insertBefore(emptyBlock, block);
                document.querySelectorAll('.script-element-block.focused').forEach(b => b.classList.remove('focused'));
                block.classList.add('focused');
                this.activeElementBlock = block;
                editable.focus();
                this.setCursorToStart(editable);
                this.hideSuggestionPopup();
                this.pushUndoSnapshot(preSnap);
                this.markDirty();
                this.calculateLiveStats();
                return;
            }

            // Case C: Cursor at the end (or action block was already empty)
            if (isCollapsed && cleanRight === '') {
                const newBlock = this.createElementBlock('action', '', block);
                const newEditable = newBlock.querySelector('.element-content:not(.d-none)') || newBlock.querySelector('.element-content');
                if (newEditable) {
                    newEditable.focus();
                    this.setCursorToStart(newEditable);
                }
                this.pushUndoSnapshot(preSnap);
                this.markDirty();
                this.calculateLiveStats();
                const seqState = this.detectCurrentSequenceState(newBlock);
                const actionSuggestions = [{ type: 'character', label: '+ Character' }];
                if (seqState.inSequence) {
                    actionSuggestions.push({ type: 'next_sequence_shot', label: '+ Next Sequence Shot' });
                    actionSuggestions.push({ type: 'end_sequence', label: 'End Sequence' });
                }
                this.showSuggestionPopup(newBlock, actionSuggestions);
                return;
            }

            // Case A (Cursor in middle) and Case D (Text selection replaced with split)
            editable.innerText = cleanLeft;
            const newBlock = this.createElementBlock('action', cleanRight, block);
            const newEditable = newBlock.querySelector('.element-content:not(.d-none)') || newBlock.querySelector('.element-content');
            if (newEditable) {
                newEditable.focus();
                this.setCursorToStart(newEditable);
            }
            this.pushUndoSnapshot(preSnap);
            this.markDirty();
            this.calculateLiveStats();

            if (cleanRight === '') {
                const seqState = this.detectCurrentSequenceState(newBlock);
                const actionSuggestions = [{ type: 'character', label: '+ Character' }];
                if (seqState.inSequence) {
                    actionSuggestions.push({ type: 'next_sequence_shot', label: '+ Next Sequence Shot' });
                    actionSuggestions.push({ type: 'end_sequence', label: 'End Sequence' });
                }
                this.showSuggestionPopup(newBlock, actionSuggestions);
            } else {
                this.hideSuggestionPopup();
            }
            return;
        }

        let nextType = 'action';
        let suggestions = [];

        if (currentType === 'scene_heading') {
            nextType = 'action';
        } else if (currentType === 'character') {
            nextType = 'dialogue';
            suggestions = [{ type: 'parenthetical', label: '+ Parenthetical' }];
        } else if (currentType === 'parenthetical') {
            if (currentText) {
                const formatted = this.formatParenthetical(currentText);
                if (editable.innerText !== formatted) {
                    editable.innerText = formatted;
                }
            }
            nextType = 'dialogue';
        } else if (currentType === 'dialogue') {
            nextType = 'action';
            suggestions = [
                { type: 'character', label: '+ Character' },
                { type: 'action', label: '+ Action' }
            ];
            const seqState = this.detectCurrentSequenceState(block);
            if (seqState.inSequence) {
                suggestions.push({ type: 'next_sequence_shot', label: '+ Next Sequence Shot' });
                suggestions.push({ type: 'end_sequence', label: 'End Sequence' });
            }
        } else if (currentType === 'transition') {
            nextType = 'action';
        } else if (currentType === 'shot') {
            nextType = 'action';
            const seqState = this.detectCurrentSequenceState(block);
            if (seqState.inSequence) {
                suggestions = [
                    { type: 'character', label: '+ Character' },
                    { type: 'next_sequence_shot', label: '+ Next Sequence Shot' }
                ];
            }
        }

        const newBlock = this.createElementBlock(nextType, '', block);
        const newEditable = newBlock.querySelector('.element-content:not(.d-none)') || newBlock.querySelector('.element-content');
        if (newEditable) {
            newEditable.focus();
            this.setCursorToStart(newEditable);
        }
        this.pushUndoSnapshot(preSnap);
        this.markDirty();
        this.calculateLiveStats();

        if (suggestions.length > 0) {
            this.showSuggestionPopup(newBlock, suggestions);
        } else {
            this.hideSuggestionPopup();
        }
    }

    cycleElementType(block, direction = 1) {
        const types = ['scene_heading', 'action', 'character', 'dialogue', 'parenthetical', 'transition', 'note'];
        const currentType = block.dataset.type;
        let index = types.indexOf(currentType);
        if (index === -1) index = 1;
        
        let newIndex = (index + direction + types.length) % types.length;
        const newType = types[newIndex];

        this.setElementType(block, newType);
    }

    setElementType(block, newType) {
        const oldType = block.dataset.type;
        if (oldType === newType) return;
        const preSnap = this.captureSnapshot();
        block.dataset.type = newType;
        const tag = block.querySelector('.element-type-tag');
        if (tag) tag.innerText = this.formatTypeLabel(newType);

        let editable = block.querySelector('.element-content');
        let currentContent = editable ? editable.innerText : '';

        // Clean up old complex structures if transitioning away
        if (oldType === 'scene_heading') {
            const lineWrapper = block.querySelector('.scene-heading-line');
            if (lineWrapper) lineWrapper.remove();
            editable = null;
        } else if (oldType === 'transition') {
            const transWrapper = block.querySelector('.transition-element-wrapper');
            if (transWrapper) {
                transWrapper.remove();
                editable = null;
            }
        } else if (oldType === 'shot') {
            const lineWrapper = block.querySelector('.sequence-shot-line');
            if (lineWrapper) lineWrapper.remove();
            block.classList.remove('sequence-shot-heading', 'sequence-marker', 'sequence-marker-start', 'sequence-marker-end');
            editable = null;
        } else if (oldType === 'parenthetical' && newType !== 'parenthetical') {
            let trimmed = currentContent.trim();
            if (trimmed.startsWith('(') && trimmed.endsWith(')') && trimmed.length >= 2) {
                currentContent = trimmed.slice(1, -1).trim();
            }
        }

        if (newType !== 'shot') {
            block.classList.remove('sequence-shot-heading', 'sequence-marker', 'sequence-marker-start', 'sequence-marker-end');
        }

        if (newType === 'scene_heading') {
            const lineWrapper = document.createElement('div');
            lineWrapper.className = 'scene-heading-line';

            const prefix = document.createElement('span');
            prefix.className = 'scene-prefix-label font-screenplay user-select-none';
            const currentSceneMeta = (this.scenesTree || []).find(s => Number(s.id) === Number(this.currentSceneId));
            const fallbackIdent = (currentSceneMeta && (currentSceneMeta.scene_identifier || currentSceneMeta.nav_identifier || currentSceneMeta.display_number))
                || (this.currentSceneIsSub ? 'Sub-Scene' : 'Scene');
            prefix.innerText = (this.currentSceneIdentifier || fallbackIdent) + ' :';
            lineWrapper.appendChild(prefix);

            if (editable) {
                editable.remove();
            } else {
                editable = document.createElement('div');
                editable.className = 'element-content font-screenplay font-malayalam';
                editable.contentEditable = 'true';
                editable.spellcheck = false;
            }
            editable.dataset.placeholder = this.getPlaceholderForType(newType);
            const cleanText = (currentContent || '').replace(/^(?:Scene\s+\d+(?:\.[A-Za-z]+)?\s*[:—\-]\s*)+/i, '').trim();
            editable.innerText = cleanText;
            lineWrapper.appendChild(editable);
            block.appendChild(lineWrapper);
            this.bindElementEvents(block, editable);
        } else if (oldType === 'scene_heading' && newType !== 'scene_heading') {
            const lineWrapper = block.querySelector('.scene-heading-line');
            if (lineWrapper) {
                lineWrapper.remove();
            }
            editable = document.createElement('div');
            editable.className = 'element-content font-screenplay font-malayalam';
            editable.contentEditable = 'true';
            editable.spellcheck = false;
            editable.dataset.placeholder = this.getPlaceholderForType(newType);
            if (newType === 'parenthetical' && currentContent.trim()) {
                editable.innerText = this.formatParenthetical(currentContent);
            } else {
                editable.innerText = currentContent;
            }
            block.appendChild(editable);
            this.bindElementEvents(block, editable);
        } else if (newType === 'transition') {
            const wrapper = document.createElement('div');
            wrapper.className = 'transition-element-wrapper';

            editable = document.createElement('div');
            editable.className = 'element-content font-screenplay font-malayalam';
            editable.contentEditable = 'true';
            editable.spellcheck = false;
            editable.dataset.placeholder = this.getPlaceholderForType(newType);
            editable.innerText = currentContent.trim() ? currentContent.trim() : 'CUT TO:';

            const pickerDropdown = document.createElement('div');
            pickerDropdown.className = 'transition-picker-dropdown dropdown';
            pickerDropdown.contentEditable = 'false';

            const toggleBtn = document.createElement('button');
            toggleBtn.className = 'btn btn-sm transition-dropdown-btn dropdown-toggle';
            toggleBtn.type = 'button';
            toggleBtn.dataset.bsToggle = 'dropdown';
            toggleBtn.dataset.bsPopperConfig = '{"strategy":"fixed"}';
            toggleBtn.title = 'Select transition';
            toggleBtn.tabIndex = -1;
            toggleBtn.innerHTML = '<i class="bi bi-chevron-down"></i>';

            const menu = document.createElement('ul');
            menu.className = 'dropdown-menu dropdown-menu-end shadow-sm small transition-options-menu';

            const standardTransitions = [
                'CUT TO:',
                'FADE IN:',
                'FADE OUT:',
                'DISSOLVE TO:',
                'SMASH CUT TO:',
                'MATCH CUT TO:',
                'INTERCUT',
                'CUT BACK TO:',
            ];

            standardTransitions.forEach(trans => {
                const li = document.createElement('li');
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'dropdown-item transition-opt-item';
                btn.innerText = trans;
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const preSnap = this.captureSnapshot();
                    editable.innerText = trans;
                    this.pushUndoSnapshot(preSnap);
                    this.markDirty();
                    this.calculateLiveStats();
                    editable.focus();
                    this.setCursorToEnd(editable);
                });
                li.appendChild(btn);
                menu.appendChild(li);
            });

            const divider = document.createElement('li');
            divider.innerHTML = '<hr class="dropdown-divider">';
            menu.appendChild(divider);

            const customLi = document.createElement('li');
            const customBtn = document.createElement('button');
            customBtn.type = 'button';
            customBtn.className = 'dropdown-item text-muted';
            customBtn.innerHTML = '<i class="bi bi-pencil me-1"></i> Custom Transition...';
            customBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                editable.focus();
                const range = document.createRange();
                range.selectNodeContents(editable);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
            });
            customLi.appendChild(customBtn);
            menu.appendChild(customLi);

            pickerDropdown.appendChild(toggleBtn);
            pickerDropdown.appendChild(menu);

            wrapper.appendChild(editable);
            wrapper.appendChild(pickerDropdown);
            block.appendChild(wrapper);

            this.bindElementEvents(block, editable);
        } else {
            if (!editable) {
                editable = document.createElement('div');
                editable.className = 'element-content font-screenplay font-malayalam';
                editable.contentEditable = 'true';
                editable.spellcheck = false;
                block.appendChild(editable);
                this.bindElementEvents(block, editable);
            }
            editable.dataset.placeholder = this.getPlaceholderForType(newType);
            if (newType === 'parenthetical') {
                editable.innerText = currentContent.trim() ? this.formatParenthetical(currentContent) : '';
            } else {
                editable.innerText = currentContent;
            }
        }

        this.updateActiveToolbarButton(newType);
        if (this.currentTypeEl) {
            this.currentTypeEl.innerText = this.formatTypeLabel(newType);
        }
        this.pushUndoSnapshot(preSnap);
        this.markDirty();
        this.calculateLiveStats();
    }

    // ----------------------------------------------------
    // CHARACTER AUTOCOMPLETE
    // ----------------------------------------------------
    handleCharacterInput(editable) {
        const text = editable.innerText.trim();
        if (!text || !this.autocompleteDropdown) {
            this.hideAutocomplete();
            return;
        }

        const matches = this.characters.filter(c => c.toLowerCase().includes(text.toLowerCase()));
        if (matches.length === 0) {
            this.hideAutocomplete();
            return;
        }

        this.autocompleteDropdown.innerHTML = '';
        this.autocompleteIndex = -1;

        matches.slice(0, 6).forEach((charName) => {
            const item = document.createElement('div');
            item.className = 'character-autocomplete-item font-screenplay font-malayalam';
            item.innerText = charName.toUpperCase();
            item.addEventListener('mousedown', (e) => {
                e.preventDefault();
                editable.innerText = charName.toUpperCase();
                this.hideAutocomplete();
                this.handleEnterKey(this.activeElementBlock, editable);
            });
            this.autocompleteDropdown.appendChild(item);
        });

        this.activeAutocompleteEditable = editable;

        // Position dropdown near the element using fixed viewport coordinates
        this.positionAutocomplete(editable);
    }

    positionAutocomplete(editable) {
        if (!this.autocompleteDropdown || !editable) return;

        const rect = editable.getBoundingClientRect();
        const vv = this.getVisibleViewport ? this.getVisibleViewport() : {
            top: 0,
            bottom: window.innerHeight,
            left: 0,
            right: window.innerWidth,
            width: window.innerWidth,
            height: window.innerHeight
        };

        this.autocompleteDropdown.style.position = 'fixed';
        this.autocompleteDropdown.style.display = 'block';

        const dropdownRect = this.autocompleteDropdown.getBoundingClientRect();
        const dropdownWidth = dropdownRect.width || 180;
        const dropdownHeight = dropdownRect.height || 140;

        const GAP = 4;
        const MARGIN_X = 12;

        // Viewport boundaries
        const minLeft = (vv.left || 0) + MARGIN_X;
        const maxLeft = Math.max(minLeft, (vv.right || window.innerWidth) - dropdownWidth - MARGIN_X);

        let leftPos = rect.left;
        leftPos = Math.max(minLeft, Math.min(leftPos, maxLeft));

        // Space above and below in viewport
        const spaceBelow = vv.bottom - (rect.bottom + GAP);
        const spaceAbove = (rect.top - GAP) - vv.top;

        let topPos;
        if (spaceBelow >= Math.min(dropdownHeight, 100)) {
            topPos = rect.bottom + GAP;
        } else if (spaceAbove >= dropdownHeight) {
            topPos = rect.top - dropdownHeight - GAP;
        } else if (spaceBelow >= spaceAbove) {
            topPos = rect.bottom + GAP;
        } else {
            topPos = rect.top - dropdownHeight - GAP;
        }

        // Hard clamp within visible viewport boundaries
        if (topPos + dropdownHeight > vv.bottom - 8) {
            topPos = Math.max(vv.top + 8, vv.bottom - dropdownHeight - 8);
        }
        if (topPos < vv.top + 8) {
            topPos = vv.top + 8;
        }

        this.autocompleteDropdown.style.left = `${Math.round(leftPos)}px`;
        this.autocompleteDropdown.style.top = `${Math.round(topPos)}px`;
    }

    navigateAutocomplete(dir) {
        if (!this.autocompleteDropdown) return;
        const items = this.autocompleteDropdown.querySelectorAll('.character-autocomplete-item');
        if (items.length === 0) return;

        items.forEach(i => i.classList.remove('active'));
        this.autocompleteIndex = (this.autocompleteIndex + dir + items.length) % items.length;
        items[this.autocompleteIndex].classList.add('active');
        items[this.autocompleteIndex].scrollIntoView({ block: 'nearest' });
    }

    selectAutocompleteItem() {
        if (!this.autocompleteDropdown) return;
        const items = this.autocompleteDropdown.querySelectorAll('.character-autocomplete-item');
        if (items.length > 0 && this.autocompleteIndex >= 0) {
            const selectedText = items[this.autocompleteIndex].innerText;
            const editable = this.activeElementBlock.querySelector('.element-content');
            editable.innerText = selectedText;
            this.hideAutocomplete();
            this.handleEnterKey(this.activeElementBlock, editable);
        } else if (items.length > 0) {
            const selectedText = items[0].innerText;
            const editable = this.activeElementBlock.querySelector('.element-content');
            editable.innerText = selectedText;
            this.hideAutocomplete();
            this.handleEnterKey(this.activeElementBlock, editable);
        }
    }

    hideAutocomplete() {
        if (this.autocompleteDropdown) {
            this.autocompleteDropdown.style.display = 'none';
        }
        this.activeAutocompleteEditable = null;
        this.autocompleteIndex = -1;
    }

    // ----------------------------------------------------
    // SCENE-LEVEL IN-MEMORY HISTORY ARCHITECTURE (Undo/Redo)
    // ----------------------------------------------------
    initSceneHistory(sceneId) {
        const sid = Number(sceneId);
        if (!sid) return;

        // Ensure no pending timers from a previously loaded scene persist
        if (this.textEditTimer) {
            clearTimeout(this.textEditTimer);
            this.textEditTimer = null;
            this.textEditTimerSceneId = null;
        }

        if (!this.undoStacks[sid]) {
            this.undoStacks[sid] = [];
        }
        if (!this.redoStacks[sid]) {
            this.redoStacks[sid] = [];
        }
        // If undoStack is empty for this scene, push the baseline snapshot
        if (this.undoStacks[sid].length === 0) {
            const baseline = this.captureSnapshot();
            if (baseline) {
                this.undoStacks[sid].push(baseline);
                this.lastCapturedSnapshot = baseline;
            }
        } else {
            this.lastCapturedSnapshot = this.undoStacks[sid][this.undoStacks[sid].length - 1];
        }
        this.updateHistoryButtonsState();
    }

    captureSnapshot() {
        if (!this.pageContainer) return null;
        const payload = this.extractScenePayload();
        // Deep clone payload to isolate state from future mutations
        return {
            heading: payload.heading,
            elements: (payload.elements || []).map(e => ({
                element_type: e.element_type,
                content: e.content,
                order: e.order
            }))
        };
    }

    areSnapshotsEqual(snapA, snapB) {
        if (!snapA || !snapB) return false;
        if (snapA.heading !== snapB.heading) return false;
        const elemsA = snapA.elements || [];
        const elemsB = snapB.elements || [];
        if (elemsA.length !== elemsB.length) return false;
        for (let i = 0; i < elemsA.length; i++) {
            if (elemsA[i].element_type !== elemsB[i].element_type) return false;
            if (elemsA[i].content !== elemsB[i].content) return false;
        }
        return true;
    }

    pushUndoSnapshot(preMutationSnapshot = null) {
        const sid = Number(this.currentSceneId);
        if (!sid) return;

        // Any structural edit commits / cancels pending debounced text edit timer
        if (this.textEditTimer) {
            clearTimeout(this.textEditTimer);
            this.textEditTimer = null;
            this.textEditTimerSceneId = null;
        }

        if (!this.undoStacks[sid]) {
            this.undoStacks[sid] = [];
        }

        const currentStack = this.undoStacks[sid];

        // If a pre-mutation snapshot was provided and it differs from top of stack, push it first
        if (preMutationSnapshot) {
            const topSnapshot = currentStack[currentStack.length - 1];
            if (!this.areSnapshotsEqual(topSnapshot, preMutationSnapshot)) {
                currentStack.push(preMutationSnapshot);
                if (currentStack.length > this.maxHistoryStack) {
                    currentStack.shift();
                }
            }
        }

        // Now capture and push the post-mutation snapshot representing the new state
        const postSnapshot = this.captureSnapshot();
        if (postSnapshot) {
            const topSnapshot = currentStack[currentStack.length - 1];
            if (!this.areSnapshotsEqual(topSnapshot, postSnapshot)) {
                currentStack.push(postSnapshot);
                if (currentStack.length > this.maxHistoryStack) {
                    currentStack.shift();
                }
            }
        }

        // New edit invalidates any future redo branch
        if (this.redoStacks[sid] && this.redoStacks[sid].length > 0) {
            this.redoStacks[sid] = [];
        }

        this.lastCapturedSnapshot = postSnapshot;
        this.updateHistoryButtonsState();
    }

    flushPendingTextEdit() {
        if (!this.textEditTimer) return;
        const targetSid = this.textEditTimerSceneId || Number(this.currentSceneId);
        clearTimeout(this.textEditTimer);
        this.textEditTimer = null;
        this.textEditTimerSceneId = null;

        if (this.isComposing) return;
        if (!targetSid || Number(this.currentSceneId) !== targetSid) return;

        const currentSnap = this.captureSnapshot();
        if (!currentSnap) return;

        if (!this.undoStacks[targetSid]) {
            this.undoStacks[targetSid] = [];
        }

        const currentStack = this.undoStacks[targetSid];
        const topSnapshot = currentStack[currentStack.length - 1];
        if (!this.areSnapshotsEqual(topSnapshot, currentSnap)) {
            currentStack.push(currentSnap);
            if (currentStack.length > this.maxHistoryStack) {
                currentStack.shift();
            }
            this.lastCapturedSnapshot = currentSnap;
        }

        // Always invalidate redo stack on flushed edit
        if (this.redoStacks[targetSid] && this.redoStacks[targetSid].length > 0) {
            this.redoStacks[targetSid] = [];
        }
        this.updateHistoryButtonsState();
    }

    recordTextEdit() {
        if (this.isComposing) return;
        const sid = Number(this.currentSceneId);
        if (!sid) return;

        // When user starts typing a new edit, immediately invalidate redo stack
        if (this.redoStacks[sid] && this.redoStacks[sid].length > 0) {
            this.redoStacks[sid] = [];
            this.updateHistoryButtonsState();
        }

        if (this.textEditTimer) {
            clearTimeout(this.textEditTimer);
            this.textEditTimer = null;
        }
        this.textEditTimerSceneId = sid;

        this.textEditTimer = setTimeout(() => {
            this.textEditTimer = null;
            const timerSid = this.textEditTimerSceneId;
            this.textEditTimerSceneId = null;

            if (this.isComposing) return;
            if (!timerSid || Number(this.currentSceneId) !== timerSid) return;

            const currentSnap = this.captureSnapshot();
            if (!currentSnap) return;

            if (!this.undoStacks[timerSid]) {
                this.undoStacks[timerSid] = [];
            }

            const currentStack = this.undoStacks[timerSid];
            const topSnapshot = currentStack[currentStack.length - 1];
            if (!this.areSnapshotsEqual(topSnapshot, currentSnap)) {
                currentStack.push(currentSnap);
                if (currentStack.length > this.maxHistoryStack) {
                    currentStack.shift();
                }
                this.lastCapturedSnapshot = currentSnap;
                if (this.redoStacks[timerSid] && this.redoStacks[timerSid].length > 0) {
                    this.redoStacks[timerSid] = [];
                }
                this.updateHistoryButtonsState();
            }
        }, 500);
    }

    undo() {
        const sid = Number(this.currentSceneId);
        if (!sid) return;

        const stack = this.undoStacks[sid] || [];
        const hadPendingTimer = Boolean(this.textEditTimer && this.textEditTimerSceneId === sid);

        // Cancel any pending debounced text edit timer
        if (this.textEditTimer) {
            clearTimeout(this.textEditTimer);
            this.textEditTimer = null;
            this.textEditTimerSceneId = null;
        }

        const currentSnap = this.captureSnapshot();
        const topSnapshot = stack[stack.length - 1];
        const isUncommittedTextEdit = hadPendingTimer && currentSnap && topSnapshot && !this.areSnapshotsEqual(topSnapshot, currentSnap);

        if (isUncommittedTextEdit) {
            // Typing occurred that has not yet been pushed to undoStacks.
            // The uncommitted DOM state becomes the state to redo.
            if (!this.redoStacks[sid]) {
                this.redoStacks[sid] = [];
            }
            const redoStack = this.redoStacks[sid];
            const topRedo = redoStack[redoStack.length - 1];
            if (!this.areSnapshotsEqual(topRedo, currentSnap)) {
                redoStack.push(currentSnap);
                if (redoStack.length > this.maxHistoryStack) {
                    redoStack.shift();
                }
            }

            // Target state to restore is the top of undoStack (state before typing began)
            this.applyHistorySnapshot(topSnapshot);
            this.lastCapturedSnapshot = topSnapshot;
            this.updateHistoryButtonsState();
            return;
        }

        // Standard undo: stack must contain at least baseline + 1 edit
        if (stack.length <= 1) return;

        if (!this.redoStacks[sid]) {
            this.redoStacks[sid] = [];
        }

        // Pop current committed state from undo stack
        stack.pop();
        const targetSnap = stack[stack.length - 1];
        if (!targetSnap) return;

        if (currentSnap) {
            const redoStack = this.redoStacks[sid];
            const topRedo = redoStack[redoStack.length - 1];
            if (!this.areSnapshotsEqual(topRedo, currentSnap)) {
                redoStack.push(currentSnap);
                if (redoStack.length > this.maxHistoryStack) {
                    redoStack.shift();
                }
            }
        }

        this.applyHistorySnapshot(targetSnap);
        this.lastCapturedSnapshot = targetSnap;
        this.updateHistoryButtonsState();
    }

    redo() {
        const sid = Number(this.currentSceneId);
        if (!sid) return;

        // Cancel pending debounced text edit before redoing
        if (this.textEditTimer) {
            clearTimeout(this.textEditTimer);
            this.textEditTimer = null;
            this.textEditTimerSceneId = null;
        }

        const redoStack = this.redoStacks[sid] || [];
        if (redoStack.length === 0) return;

        const targetSnap = redoStack.pop();
        if (!targetSnap) return;

        if (!this.undoStacks[sid]) {
            this.undoStacks[sid] = [];
        }
        this.undoStacks[sid].push(targetSnap);
        if (this.undoStacks[sid].length > this.maxHistoryStack) {
            this.undoStacks[sid].shift();
        }

        this.applyHistorySnapshot(targetSnap);
        this.lastCapturedSnapshot = targetSnap;
        this.updateHistoryButtonsState();
    }

    applyHistorySnapshot(snapshot) {
        if (!snapshot || !this.pageContainer) return;

        // Remember currently focused element index
        let focusedIndex = 0;
        const blocks = Array.from(this.pageContainer.querySelectorAll('.script-element-block'));
        const focusedBlock = this.activeElementBlock || this.pageContainer.querySelector('.script-element-block.focused');
        if (focusedBlock) {
            const idx = blocks.indexOf(focusedBlock);
            if (idx >= 0) focusedIndex = idx;
        }

        const sid = Number(this.currentSceneId);
        const sceneMeta = (this.scenesTree || []).find(s => Number(s.id) === sid) || { id: sid, heading: snapshot.heading };
        const dummyScene = Object.assign({}, sceneMeta, { id: sid, heading: snapshot.heading });

        this.renderSceneElements(dummyScene, snapshot.elements);

        // Restore focus to closest corresponding block
        const newBlocks = Array.from(this.pageContainer.querySelectorAll('.script-element-block'));
        const targetBlock = newBlocks[Math.min(focusedIndex, newBlocks.length - 1)];
        if (targetBlock) {
            newBlocks.forEach(b => b.classList.remove('focused'));
            targetBlock.classList.add('focused');
            this.activeElementBlock = targetBlock;
            const ed = targetBlock.querySelector('.element-content:not(.d-none)') || targetBlock.querySelector('.element-content, .heading-location-input');
            if (ed) {
                ed.focus();
                this.setCursorToEnd(ed);
            }
        }

        // Feed standard save pipeline & Read Mode sync
        this.markDirty();
        this.calculateLiveStats();
        const payload = this.extractScenePayload();
        this.updateReadModeScene(sid, payload);
    }

    updateHistoryButtonsState() {
        const sid = Number(this.currentSceneId);
        const undoStack = (sid && this.undoStacks[sid]) || [];
        const redoStack = (sid && this.redoStacks[sid]) || [];

        const hasUncommittedEdit = Boolean(this.textEditTimer && this.textEditTimerSceneId === sid);
        const canUndo = undoStack.length > 1 || (undoStack.length === 1 && hasUncommittedEdit);
        const canRedo = redoStack.length > 0;

        const btnUndo = document.getElementById('btnToolbarUndo');
        if (btnUndo) {
            btnUndo.disabled = !canUndo;
            btnUndo.classList.toggle('disabled', !canUndo);
        }

        const btnRedo = document.getElementById('btnToolbarRedo');
        if (btnRedo) {
            btnRedo.disabled = !canRedo;
            btnRedo.classList.toggle('disabled', !canRedo);
        }
    }


    // ----------------------------------------------------
    // ROBUST AUTO-SAVE & PERSISTENCE (Task 7 Architecture)
    // ----------------------------------------------------
    markDirty() {
        this.changeVersion = (this.changeVersion || 0) + 1;
        this.isDirty = true;
        this.setSaveStatus('dirty', 'Unsaved changes');
        
        clearTimeout(this.saveTimeout);
        this.saveTimeout = setTimeout(() => {
            this.saveCurrentScene();
        }, 1500);
    }

    extractScenePayload() {
        const blocks = this.pageContainer.querySelectorAll('.script-element-block');
        const elementsData = [];
        let sceneHeading = this.currentSceneIsSequence
            ? (this.currentSceneHeading || (this.currentSceneSequenceType === 'montage' ? 'MONTAGE BEGINS' : 'SONG BEGINS'))
            : 'INT. LOCATION - DAY';

        if (!Array.from(blocks).some(b => b.dataset.type === 'scene_heading')) {
            const firstShot = Array.from(blocks).find(b => b.dataset.type === 'shot');
            const firstContent = (firstShot?.querySelector('.element-content')?.innerText || '').trim().toUpperCase();
            if (firstContent === 'SONG BEGINS' || firstContent === 'MONTAGE BEGINS') {
                sceneHeading = firstContent;
            }
        }

        blocks.forEach((block, index) => {
            const type = block.dataset.type;
            let content = '';

            if (type === 'scene_heading') {
                const intextSel = block.querySelector('.heading-intext-select');
                const locInp = block.querySelector('.heading-location-input');
                const timeSel = block.querySelector('.heading-time-select');
                if (intextSel && locInp && timeSel) {
                    const intext = intextSel.value || 'INT.';
                    const loc = locInp.value.trim();
                    const time = timeSel.value || 'DAY';
                    content = this.buildHeading(intext, loc || 'LOCATION', time);
                    sceneHeading = content;
                } else {
                    const contentEl = block.querySelector('.element-content');
                    content = contentEl ? contentEl.innerText.replace(/^(?:Scene\s+\d+(?:\.[A-Za-z]+)?\s*[:—\-]\s*)+/i, '').trim() : 'INT. LOCATION - DAY';
                    sceneHeading = content || 'INT. LOCATION - DAY';
                }
            } else if (type === 'note') {
                const contentEl = block.querySelector('.element-content');
                content = contentEl ? contentEl.innerText.replace(/\r\n/g, '\n').trimEnd() : '';
            } else if (type === 'shot' && block.classList.contains('sequence-shot-heading')) {
                const numSpan = block.querySelector('.sequence-shot-number');
                const intextSel = block.querySelector('.heading-intext-select');
                const locInp = block.querySelector('.heading-location-input');
                const timeSel = block.querySelector('.heading-time-select');
                if (numSpan && intextSel && locInp && timeSel) {
                    const rawNum = (numSpan.innerText || '').replace('.', '').trim() || '1';
                    const intext = intextSel.value || 'INT.';
                    const loc = locInp.value.trim();
                    const time = timeSel.value || 'DAY';
                    const headingStr = this.buildHeading(intext, loc || 'LOCATION', time);
                    content = `${rawNum}. ${headingStr || `${intext} ${loc || 'LOCATION'} - ${time}`}`;
                } else {
                    const contentEl = block.querySelector('.element-content');
                    content = contentEl ? contentEl.innerText.trim() : '';
                }
            } else {
                const contentEl = block.querySelector('.element-content');
                content = contentEl ? contentEl.innerText.trim() : '';
                if (type === 'parenthetical' && content) {
                    content = this.formatParenthetical(content);
                }
            }

            elementsData.push({
                element_type: type,
                content: content,
                order: index,
            });
        });

        return {
            heading: sceneHeading,
            elements: elementsData,
        };
    }

    getMainSceneIdForScene(sceneId) {
        if (!this.scenesTree || !sceneId) return Number(sceneId);
        const sid = Number(sceneId);
        const directMatch = this.scenesTree.find(s => Number(s.id) === sid);
        if (directMatch) {
            if (directMatch.is_sub_scene && directMatch.parent_scene_id) {
                return Number(directMatch.parent_scene_id);
            }
            return Number(directMatch.id);
        }
        for (const mainSc of this.scenesTree) {
            if (Number(mainSc.id) === sid) return Number(mainSc.id);
            if (mainSc.sub_scenes && Array.isArray(mainSc.sub_scenes)) {
                for (const subSc of mainSc.sub_scenes) {
                    if (Number(subSc.id) === sid) return Number(mainSc.id);
                }
            }
        }
        return sid;
    }

    getMainSceneOrderIds() {
        if (!this.scenesTree) return [];
        return this.scenesTree
            .filter(sc => !sc.is_sub_scene && !sc.parent_scene_id)
            .map(sc => Number(sc.id));
    }

    getOrderedSceneIds() {
        const ids = [];
        if (!this.scenesTree) return ids;
        this.scenesTree.forEach(mainSc => {
            ids.push(Number(mainSc.id));
            if (mainSc.sub_scenes && mainSc.sub_scenes.length > 0) {
                mainSc.sub_scenes.forEach(subSc => {
                    ids.push(Number(subSc.id));
                });
            }
        });
        return ids;
    }

    ensurePreviousSceneHasTransition() {
        if (this.currentSceneIsSequence) return null;
        const blocks = Array.from(this.pageContainer.querySelectorAll('.script-element-block'));
        if (blocks.length === 0) return null;

        // Check if there is already a non-empty transition element
        const hasTransition = blocks.some(b => {
            if (b.dataset.type === 'transition') {
                const text = b.querySelector('.element-content')?.innerText.trim();
                return Boolean(text);
            }
            return false;
        });

        if (hasTransition) {
            return null;
        }

        // Find the last non-note element block to insert the transition after
        let targetBlock = null;
        for (let i = blocks.length - 1; i >= 0; i--) {
            if (blocks[i].dataset.type !== 'note') {
                targetBlock = blocks[i];
                break;
            }
        }

        if (targetBlock) {
            const targetContent = (targetBlock.querySelector('.element-content')?.innerText || '').trim().toUpperCase();
            if (targetContent === 'SONG ENDS' || targetContent === 'MONTAGE ENDS' ||
                targetContent === 'SONG BEGINS' || targetContent === 'MONTAGE BEGINS' ||
                targetBlock.classList.contains('sequence-marker') || targetBlock.classList.contains('sequence-marker-end')) {
                return null;
            }
        }

        if (!targetBlock) {
            targetBlock = blocks[blocks.length - 1];
        }

        const newBlock = this.createElementBlock('transition', 'CUT TO:', targetBlock);
        this.markDirty();
        this.calculateLiveStats();
        return newBlock;
    }

    async saveCurrentScene(force = false) {
        if (!this.isDirty && !force && !this.isSaving) {
            this.setSaveStatus('saved', 'Saved ✓');
            return Promise.resolve();
        }

        if (!navigator.onLine) {
            this.setSaveStatus('offline', 'Offline / connection problem');
            return Promise.reject(new Error('Device is offline'));
        }

        // Canvas-to-Save-Target Integrity Guard
        const targetSceneId = Number(this.currentSceneId);
        const canvasLoadedId = this.pageContainer && this.pageContainer.dataset ? Number(this.pageContainer.dataset.loadedSceneId) : null;

        if (!canvasLoadedId || isNaN(canvasLoadedId)) {
            console.error(`Canvas integrity check failed: canvas has no loadedSceneId for save target ${targetSceneId}`);
            this.setSaveStatus('error', 'Scene not loaded. Save aborted.');
            return Promise.reject(new Error(`Data integrity violation: Canvas has no loaded scene for save target ${targetSceneId}`));
        }

        if (canvasLoadedId !== targetSceneId) {
            console.error(`Canvas integrity check failed: canvas loadedSceneId (${canvasLoadedId}) does not match currentSceneId (${targetSceneId})`);
            this.setSaveStatus('error', 'Integrity error: scene mismatch. Save aborted.');
            return Promise.reject(new Error(`Data integrity violation: Canvas loaded scene ${canvasLoadedId} does not match save target ${targetSceneId}`));
        }

        if (this.isSaving && this.activeSavePromise) {
            this.needsQueuedSave = true;
            return this.activeSavePromise.then(() => {
                if (this.isDirty) {
                    return this.saveCurrentScene(force);
                }
            });
        }

        clearTimeout(this.saveTimeout);
        this.isSaving = true;
        this.needsQueuedSave = false;
        this.setSaveStatus('saving', 'Saving...');

        const saveVersion = this.changeVersion || 0;
        const payload = this.extractScenePayload();
        this.sceneSaveCounters = this.sceneSaveCounters || {};
        this.sceneSaveCounters[targetSceneId] = (this.sceneSaveCounters[targetSceneId] || 0) + 1;
        const saveToken = this.sceneSaveCounters[targetSceneId];

        this.activeSavePromise = (async () => {
            try {
                const res = await fetch(`/scripts/api/${this.scriptId}/scenes/${targetSceneId}/save/`, {
                    method: 'POST',
                    headers: this.getHeaders(),
                    body: JSON.stringify(payload)
                });

                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    throw new Error(errData.message || `Server returned HTTP ${res.status}`);
                }

                const result = await res.json();
                if (result.status !== 'ok') {
                    throw new Error(result.message || 'Save failed');
                }

                const isLatestSaveForScene = (this.sceneSaveCounters[targetSceneId] === saveToken);
                const isActiveScene = (Number(this.currentSceneId) === targetSceneId);
                const hasNewerUnsavedEdits = isActiveScene && ((this.changeVersion || 0) !== saveVersion);

                if (isActiveScene) {
                    if (hasNewerUnsavedEdits) {
                        this.isDirty = true;
                        this.setSaveStatus('dirty', 'Unsaved changes');
                    } else {
                        this.isDirty = false;
                        this.setSaveStatus('saved', 'Saved ✓');
                    }
                }

                // Synchronize in-memory tree and sidebar with persisted location from server
                if (isLatestSaveForScene && !hasNewerUnsavedEdits) {
                    const treeItem = (this.scenesTree || []).find(sc => Number(sc.id) === Number(targetSceneId));
                    if (treeItem) {
                        if (result.clean_location) {
                            treeItem.clean_location = result.clean_location;
                        }
                        if (result.clean_heading) {
                            treeItem.clean_heading = result.clean_heading;
                        }
                        if (result.heading) {
                            treeItem.heading = result.heading;
                        }
                        if (result.full_display_heading) {
                            treeItem.full_display_heading = result.full_display_heading;
                        }
                        if (result.scene_identifier) {
                            treeItem.scene_identifier = result.scene_identifier;
                        }
                        if (result.nav_identifier) {
                            treeItem.nav_identifier = result.nav_identifier;
                        }
                        if (result.display_number) {
                            treeItem.display_number = result.display_number;
                        }
                        if (result.display_number_formatted) {
                            treeItem.display_number_formatted = result.display_number_formatted;
                        }
                        if (result.transition) {
                            treeItem.transition = result.transition;
                        }
                    }

                    const activeSidebarLocs = document.querySelectorAll(`.scene-item[data-id="${targetSceneId}"] .scene-nav-location`);
                    activeSidebarLocs.forEach(item => {
                        item.innerText = result.clean_location || 'Location';
                        item.title = result.clean_location || 'Location';
                    });

                    const activeSidebarNumbers = document.querySelectorAll(`.scene-item[data-id="${targetSceneId}"] .scene-nav-number`);
                    const navNumber = result.nav_identifier || result.scene_identifier;
                    if (navNumber) {
                        activeSidebarNumbers.forEach(item => {
                            item.innerText = navNumber;
                        });
                    }

                    if (result.action_preview !== undefined) {
                        if (treeItem) {
                            treeItem.action_preview = result.action_preview || '';
                        }
                        const sceneCards = document.querySelectorAll(`.scene-item[data-id="${targetSceneId}"]`);
                        sceneCards.forEach(card => {
                            const navItem = card.querySelector('.scene-nav-item');
                            if (!navItem) return;
                            let previewEl = navItem.querySelector('.scene-nav-action-preview');
                            const previewText = (result.action_preview || '').trim();
                            if (previewText) {
                                if (!previewEl) {
                                    previewEl = document.createElement('span');
                                    previewEl.className = 'scene-nav-action-preview font-malayalam';
                                    navItem.appendChild(previewEl);
                                }
                                previewEl.innerText = previewText;
                                previewEl.title = previewText;
                            } else if (previewEl) {
                                previewEl.remove();
                            }
                        });
                    }

                    if (result.heading) {
                        const sceneCards = document.querySelectorAll(`.scene-item[data-id="${targetSceneId}"]`);
                        sceneCards.forEach(card => {
                            card.querySelectorAll('.btn-action-insert-before, .btn-action-insert-after, .btn-action-add-sub, .btn-action-delete, .btn-action-rename').forEach(btn => {
                                btn.dataset.heading = result.heading;
                            });
                        });
                    }

                    if (isActiveScene) {
                        if (result.scene_identifier) {
                            this.currentSceneIdentifier = result.scene_identifier;
                        }
                        if (result.full_display_heading) {
                            this.currentFullHeading = result.full_display_heading;
                        } else if (result.clean_heading) {
                            this.currentFullHeading = `${this.currentSceneIdentifier} : ${result.clean_heading}`;
                        }
                        if (this.currentSelectorBadge && this.currentFullHeading) {
                            this.currentSelectorBadge.innerText = this.currentFullHeading;
                        }
                    }
                }

                this.updateStats(result.script_stats);
                this.updateReadModeScene(targetSceneId, payload);
                return result;
            } catch (err) {
                console.error('Save error:', err);
                const isIntegrityError = err && err.message && err.message.includes('Data integrity violation');
                const isOffline = !navigator.onLine;
                this.setSaveStatus(
                    isIntegrityError ? 'error' : (isOffline ? 'offline' : 'error'),
                    isIntegrityError ? 'Integrity error: save aborted' : (isOffline ? 'Offline / connection problem' : 'Save failed (click to retry)')
                );

                clearTimeout(this.saveTimeout);
                if (!isIntegrityError) {
                    this.saveTimeout = setTimeout(() => {
                        if (this.isDirty) {
                            this.saveCurrentScene();
                        }
                    }, 4000);
                }

                throw err;
            } finally {
                this.isSaving = false;
                this.activeSavePromise = null;
            }
        })();

        return this.activeSavePromise;
    }

    async flushSave() {
        clearTimeout(this.saveTimeout);
        while (this.isSaving && this.activeSavePromise) {
            await this.activeSavePromise.catch(() => {});
        }
        let attempts = 0;
        while (this.isDirty && attempts < 5) {
            attempts++;
            await this.saveCurrentScene(true);
        }
        if (this.isDirty) {
            throw new Error('Could not save current scene changes after multiple attempts');
        }
    }

    setSaveStatus(state, label) {
        if (!this.saveBadge) return;
        this.saveBadge.className = `save-status-badge ${state}`;
        this.saveBadge.innerHTML = state === 'saving' 
            ? `<span class="spinner-border spinner-border-sm" role="status" style="width: 0.8rem; height: 0.8rem;"></span> ${label}`
            : label;
    }

    // ----------------------------------------------------
    // HIERARCHICAL SCENE RENDERING & SWITCHING
    // ----------------------------------------------------
    renderScenesTree(tree) {
        if (!tree) return;
        this.scenesTree = tree;

        // Synchronize continuous Read Mode DOM (#readModeContainer) with authoritative tree
        this.syncReadModeWithScenesTree(tree);

        let primaryCount = 0;
        let subCount = 0;
        const htmlChunks = [];
        tree.forEach((sc) => {
            if (!sc.is_intercut) {
                if (sc.is_sub_scene) {
                    subCount++;
                } else {
                    primaryCount++;
                }
            }
            const activeId = (this.editorMode === 'read') ? Number(this.readModeActiveSceneId) : Number(this.currentSceneId);
            const isActive = Number(sc.id) === activeId;
            const isSub = Boolean(sc.is_sub_scene);
            const navId = sc.nav_identifier || sc.scene_identifier || `Scene ${sc.scene_number || ''}`;
            const cleanLoc = sc.clean_location || sc.clean_heading || sc.heading || 'Scene';
            const escapedHeading = (sc.heading || '').replace(/"/g, '&quot;');
            const parentId = sc.parent_scene_id || sc.id;

            const beforeLabel = isSub ? 'Insert Sub-Scene Before' : 'Insert Scene Before';
            const afterLabel = isSub ? 'Insert Sub-Scene After' : 'Insert Scene After';
            const targetParentId = isSub ? parentId : sc.id;

            const actionsMenuHtml = `
                <div class="scene-item-actions dropdown">
                    <button class="btn btn-sm btn-link text-muted p-0 border-0 dropdown-toggle scene-action-btn" type="button"
                        data-bs-toggle="dropdown" data-bs-popper-config='{"strategy":"fixed"}' aria-expanded="false" title="Scene Actions" aria-label="Scene Actions">
                        <i class="bi bi-three-dots-vertical"></i>
                    </button>
                    <ul class="dropdown-menu dropdown-menu-end shadow-sm small">
                        <li><button type="button" class="dropdown-item btn-action-insert-before" data-id="${sc.id}" data-is-sub="${isSub}" data-heading="${escapedHeading}"><i class="bi bi-arrow-up-circle me-2 text-primary"></i>${beforeLabel}</button></li>
                        <li><button type="button" class="dropdown-item btn-action-insert-after" data-id="${sc.id}" data-is-sub="${isSub}" data-heading="${escapedHeading}"><i class="bi bi-arrow-down-circle me-2 text-success"></i>${afterLabel}</button></li>
                        <li><button type="button" class="dropdown-item btn-action-add-sub" data-id="${targetParentId}" data-heading="${escapedHeading}"><i class="bi bi-diagram-3 me-2 text-info"></i>Add Sub-Scene</button></li>
                        <li><hr class="dropdown-divider"></li>
                        ${isSub ? `
                        <li><button type="button" class="dropdown-item btn-action-promote ${sc.is_duplicate || sc.is_intercut ? 'text-muted' : 'text-primary fw-medium'}" data-id="${sc.id}" data-badge="${navId}" data-heading="${escapedHeading}" data-is-dup="${Boolean(sc.is_duplicate)}" data-is-intercut="${Boolean(sc.is_intercut)}"><i class="bi bi-box-arrow-up-right me-2 ${sc.is_duplicate || sc.is_intercut ? 'text-muted' : 'text-primary'}"></i>Promote to Main Scene</button></li>
                        ${!sc.is_duplicate && !sc.is_intercut ? `
                        <li><button type="button" class="dropdown-item btn-action-reorder-sub" data-id="${sc.id}" data-badge="${navId}" data-heading="${escapedHeading}"><i class="bi bi-sort-numeric-down me-2 text-info"></i>Change Position</button></li>
                        ` : ''}
                        ` : ''}
                        <li><button type="button" class="dropdown-item btn-action-rename" data-id="${sc.id}" data-badge="${navId}" data-is-sub="${isSub}" data-heading="${escapedHeading}" data-is-dup="${Boolean(sc.is_duplicate)}" data-is-intercut="${Boolean(sc.is_intercut)}"><i class="bi bi-pencil me-2 text-warning"></i>Rename</button></li>
                        <li><button type="button" class="dropdown-item btn-action-copy-scene" data-id="${sc.id}"><i class="bi bi-clipboard me-2 text-secondary"></i>Copy Full Scene</button></li>
                        <li><button type="button" class="dropdown-item btn-action-dup" data-id="${sc.id}"><i class="bi bi-copy me-2 text-secondary"></i>Duplicate</button></li>
                        <li><button type="button" class="dropdown-item btn-action-move-up" data-id="${sc.id}"><i class="bi bi-arrow-up me-2"></i>Move Up</button></li>
                        <li><button type="button" class="dropdown-item btn-action-move-down" data-id="${sc.id}"><i class="bi bi-arrow-down me-2"></i>Move Down</button></li>
                        <li><hr class="dropdown-divider"></li>
                        <li><button type="button" class="dropdown-item text-danger btn-action-delete" data-id="${sc.id}" data-badge="${navId}" data-is-sub="${isSub}" data-heading="${escapedHeading}"><i class="bi bi-trash me-2"></i>Move to Trash</button></li>
                    </ul>
                </div>
            `;

            const actionPreview = sc.action_preview ? sc.action_preview.trim() : '';
            const escapedActionPreview = actionPreview.replace(/"/g, '&quot;');
            const actionPreviewHtml = actionPreview ? `<span class="scene-nav-action-preview font-malayalam" title="${escapedActionPreview}">${actionPreview}</span>` : '';

            htmlChunks.push(`
                <li class="scene-item ${isSub ? 'sub-scene-item' : ''} ${isActive ? 'active' : ''}" data-id="${sc.id}" data-parent="${sc.parent_scene_id || ''}">
                    <div class="scene-nav-item">
                        <span class="scene-nav-number font-screenplay">${navId}</span>
                        <span class="scene-nav-location font-malayalam" title="${cleanLoc.replace(/"/g, '&quot;')}">${cleanLoc}</span>
                        ${actionPreviewHtml}
                    </div>
                    ${actionsMenuHtml}
                </li>
            `);
        });

        const listHtml = htmlChunks.join('');

        if (this.scenesList) {
            this.scenesList.innerHTML = listHtml;
            this.bindSceneItemEvents(this.scenesList);
        }
        if (this.offcanvasScenesList) {
            this.offcanvasScenesList.innerHTML = listHtml;
            this.bindSceneItemEvents(this.offcanvasScenesList);
        }

        this.updateNavHeadingCounts(primaryCount, subCount);
        if (this.sceneCountEl) {
            this.sceneCountEl.innerText = subCount > 0 ? `${primaryCount} (${subCount} sub)` : `${primaryCount}`;
        }
    }

    syncReadModeWithScenesTree(tree) {
        if (!this.readModeContainer || !Array.isArray(tree)) return;

        const validIds = new Set(tree.map(s => Number(s.id)));

        // 1. Remove deleted scenes from #readModeContainer DOM
        const existingSections = this.readModeContainer.querySelectorAll('.read-mode-scene');
        existingSections.forEach(sec => {
            const secId = Number(sec.dataset.sceneId);
            if (!validIds.has(secId)) {
                sec.remove();
            }
        });

        // 2. Re-order and sync headings for each scene in authoritative order
        tree.forEach(sc => {
            const scId = Number(sc.id);
            let sec = document.getElementById(`read-scene-${scId}`);
            if (!sec) {
                sec = document.createElement('section');
                sec.className = 'read-mode-scene';
                sec.id = `read-scene-${scId}`;
                sec.dataset.sceneId = scId;

                const headingDiv = document.createElement('div');
                headingDiv.className = 'read-scene-heading font-screenplay';
                const idSpan = document.createElement('span');
                idSpan.className = 'read-scene-identifier';
                headingDiv.appendChild(idSpan);
                sec.appendChild(headingDiv);

                const elementsDiv = document.createElement('div');
                elementsDiv.className = 'read-scene-elements';
                sec.appendChild(elementsDiv);
            }

            // Append ensures DOM order strictly matches tree order without duplication
            this.readModeContainer.appendChild(sec);

            // Update heading identifier
            const headingEl = sec.querySelector('.read-scene-identifier');
            if (headingEl) {
                const fullHeading = sc.full_display_heading ||
                    `${sc.scene_identifier || sc.display_number_formatted || ('Scene ' + sc.scene_number)} : ${sc.clean_heading || sc.heading || 'UNTITLED SCENE'}`;
                headingEl.innerText = fullHeading;
            }

            // Update transition if present (only if the scene does not already end with an explicit transition)
            const elementsContainer = sec.querySelector('.read-scene-elements');
            let hasEndingTransition = false;
            if (elementsContainer) {
                const elementBlocks = Array.from(elementsContainer.querySelectorAll(':scope > .read-element-block'));
                for (let i = elementBlocks.length - 1; i >= 0; i--) {
                    const block = elementBlocks[i];
                    const content = (block.querySelector('.element-content')?.innerText || '').trim();
                    if (!content) continue;
                    if (block.classList.contains('element-type-note')) continue;
                    if (block.classList.contains('element-type-transition')) {
                        hasEndingTransition = true;
                    }
                    break;
                }
            }
            let transEl = Array.from(sec.children).find(child => child.classList && child.classList.contains('read-element-block') && child.classList.contains('element-type-transition'));
            const transitionText = (sc.transition === null || sc.transition === undefined) ? '' : String(sc.transition).trim();
            if (transitionText && !hasEndingTransition) {
                if (!transEl) {
                    transEl = document.createElement('div');
                    transEl.className = 'read-element-block element-type-transition';
                    const transContent = document.createElement('div');
                    transContent.className = 'element-content font-screenplay';
                    transEl.appendChild(transContent);
                    sec.appendChild(transEl);
                }
                const transContent = transEl.querySelector('.element-content');
                if (transContent) {
                    transContent.innerText = transitionText;
                }
            } else if (transEl) {
                transEl.remove();
            }
        });

        this.setupReadModeScrollObserver();
    }

    updateNavHeadingCounts(primaryCount, subCount) {
        if (this.sidebarSceneHeadingTextEl) {
            this.sidebarSceneHeadingTextEl.innerHTML = subCount > 0
                ? `Scenes (<span id="sidebarSceneCount">${primaryCount}</span>) · Sub-scenes (<span id="sidebarSubSceneCount">${subCount}</span>)`
                : `Scenes (<span id="sidebarSceneCount">${primaryCount}</span>)`;
            this.sidebarSceneCountEl = document.getElementById('sidebarSceneCount');
        } else if (this.sidebarSceneCountEl) {
            this.sidebarSceneCountEl.innerText = primaryCount;
        }

        if (this.offcanvasSceneHeadingTextEl) {
            this.offcanvasSceneHeadingTextEl.innerHTML = subCount > 0
                ? `Scenes (<span id="offcanvasSceneCount">${primaryCount}</span>) · Sub-scenes (<span id="offcanvasSubSceneCount">${subCount}</span>)`
                : `Scenes (<span id="offcanvasSceneCount">${primaryCount}</span>)`;
            this.offcanvasSceneCountEl = document.getElementById('offcanvasSceneCount');
        } else if (this.offcanvasSceneCountEl) {
            this.offcanvasSceneCountEl.innerText = primaryCount;
        }
    }

    bindSceneItemEvents(container) {
        if (!container || container.dataset.boundEvents === 'true') return;
        container.dataset.boundEvents = 'true';

        container.addEventListener('click', async (e) => {
            // 1. Insert Before
            const insertBeforeBtn = e.target.closest('.btn-action-insert-before');
            if (insertBeforeBtn) {
                e.preventDefault();
                const isSub = insertBeforeBtn.dataset.isSub === 'true';
                this.openInsertModal(insertBeforeBtn.dataset.id, 'before', insertBeforeBtn.dataset.heading, isSub);
                return;
            }

            // 2. Insert After
            const insertAfterBtn = e.target.closest('.btn-action-insert-after');
            if (insertAfterBtn) {
                e.preventDefault();
                const isSub = insertAfterBtn.dataset.isSub === 'true';
                this.openInsertModal(insertAfterBtn.dataset.id, 'after', insertAfterBtn.dataset.heading, isSub);
                return;
            }

            // 3. Add Sub Scene
            const addSubBtn = e.target.closest('.btn-action-add-sub');
            if (addSubBtn) {
                e.preventDefault();
                this.openSubSceneModal(addSubBtn.dataset.id, addSubBtn.dataset.heading);
                return;
            }

            // Promote Sub-Scene
            const promoteBtn = e.target.closest('.btn-action-promote');
            if (promoteBtn) {
                e.preventDefault();
                const isDup = promoteBtn.dataset.isDup === 'true';
                const isIntercut = promoteBtn.dataset.isIntercut === 'true';
                this.openPromoteModal(promoteBtn.dataset.id, promoteBtn.dataset.badge, promoteBtn.dataset.heading, isDup, isIntercut);
                return;
            }

            // Reorder Sub-Scene
            const reorderSubBtn = e.target.closest('.btn-action-reorder-sub');
            if (reorderSubBtn) {
                e.preventDefault();
                const heading = reorderSubBtn.dataset.heading || '';
                const badge = reorderSubBtn.dataset.badge || 'Sub-Scene';
                this.openRenameModal(reorderSubBtn.dataset.id, badge, heading, true, true);
                return;
            }

            // Rename Scene
            const renameBtn = e.target.closest('.btn-action-rename');
            if (renameBtn) {
                e.preventDefault();
                const isSub = renameBtn.dataset.isSub === 'true';
                const heading = renameBtn.dataset.heading || '';
                const badge = renameBtn.dataset.badge || (isSub ? 'Sub-Scene' : 'Scene');
                this.openRenameModal(renameBtn.dataset.id, badge, heading, isSub);
                return;
            }

            // 4. Move Up
            const moveUpBtn = e.target.closest('.btn-action-move-up');
            if (moveUpBtn && !moveUpBtn.classList.contains('disabled')) {
                e.preventDefault();
                await this.moveScene(moveUpBtn.dataset.id, 'up');
                return;
            }

            // 5. Move Down
            const moveDownBtn = e.target.closest('.btn-action-move-down');
            if (moveDownBtn && !moveDownBtn.classList.contains('disabled')) {
                e.preventDefault();
                await this.moveScene(moveDownBtn.dataset.id, 'down');
                return;
            }

            // 6. Copy Full Scene
            const copySceneBtn = e.target.closest('.btn-action-copy-scene');
            if (copySceneBtn) {
                e.preventDefault();
                e.stopPropagation();
                await this.copyFullScene(copySceneBtn.dataset.id);
                return;
            }

            // 7. Duplicate
            const dupBtn = e.target.closest('.btn-action-dup');
            if (dupBtn) {
                e.preventDefault();
                await this.duplicateScene(dupBtn.dataset.id);
                return;
            }

            // 7. Delete
            const delBtn = e.target.closest('.btn-action-delete');
            if (delBtn) {
                e.preventDefault();
                const isSub = delBtn.dataset.isSub === 'true';
                const heading = delBtn.dataset.heading || '';
                const badge = delBtn.dataset.badge || (isSub ? 'Sub-Scene' : 'Scene');
                this.openDeleteModal(delBtn.dataset.id, badge, heading, isSub);
                return;
            }

            // Switch scene if clicked on the scene item row (outside dropdown)
            if (e.target.closest('.scene-item-actions') || e.target.closest('.dropdown-menu') || e.target.closest('.dropdown-toggle')) {
                return;
            }
            const item = e.target.closest('.scene-item');
            if (item) {
                const sceneId = item.dataset.id;
                if (this.editorMode === 'read') {
                    // In Read Mode: smooth scroll to stable scene anchor without altering edit canvas currentSceneId
                    this.readModeActiveSceneId = Number(sceneId);
                    document.querySelectorAll('.scene-item').forEach(el => {
                        el.classList.toggle('active', Number(el.dataset.id) === Number(sceneId));
                    });
                    this.isNavigatingToScene = true;
                    clearTimeout(this._navSceneTimer);
                    this._navSceneTimer = setTimeout(() => { this.isNavigatingToScene = false; }, 600);
                    const targetEl = document.getElementById(`read-scene-${sceneId}`);
                    if (targetEl) {
                        targetEl.scrollIntoView({
                            behavior: 'smooth',
                            block: 'start'
                        });
                    }
                    if (this.bsOffcanvas && this.offcanvasEl && this.offcanvasEl.classList.contains('show')) {
                        this.bsOffcanvas.hide();
                    }
                } else {
                    document.querySelectorAll('.scene-item').forEach(el => {
                        el.classList.toggle('active', String(el.dataset.id) === String(sceneId));
                    });
                    await this.switchScene(sceneId);
                    if (this.bsOffcanvas && this.offcanvasEl && this.offcanvasEl.classList.contains('show')) {
                        this.bsOffcanvas.hide();
                    }
                }
            }
        });
    }

    async switchScene(newSceneId) {
        const targetId = Number(newSceneId);
        if (isNaN(targetId)) return;
        const canvasLoadedId = this.pageContainer && this.pageContainer.dataset ? Number(this.pageContainer.dataset.loadedSceneId) : null;
        if (!this.isSwitchingScene && targetId === Number(this.currentSceneId) && canvasLoadedId === targetId) return;

        if (this.isSwitchingScene) {
            this.pendingSwitchSceneId = targetId;
            document.querySelectorAll('.scene-item').forEach(item => {
                item.classList.toggle('active', Number(item.dataset.id) === targetId);
            });
            while (this.isSwitchingScene) {
                try {
                    await this.activeSwitchPromise;
                } catch (e) {
                    break;
                }
            }
            return;
        }

        this.isSwitchingScene = true;
        this.activeSwitchPromise = (async () => {
            const currentMainId = this.getMainSceneIdForScene(this.currentSceneId);
            const targetMainId = this.getMainSceneIdForScene(targetId);
            const mainOrder = this.getMainSceneOrderIds();
            const currentMainIdx = mainOrder.indexOf(currentMainId);
            const targetMainIdx = mainOrder.indexOf(targetMainId);

            let addedTransition = null;
            if (currentMainIdx !== -1 && targetMainIdx !== -1 && targetMainIdx > currentMainIdx) {
                addedTransition = this.ensurePreviousSceneHasTransition();
            }

            this.flushPendingTextEdit();

            try {
                await this.flushSave();
                if (this.currentSceneId) {
                    const payload = this.extractScenePayload();
                    this.updateReadModeScene(this.currentSceneId, payload);
                }
            } catch (err) {
                console.error('Save failed before switching scene:', err);
                if (addedTransition && addedTransition.parentElement) {
                    addedTransition.remove();
                    this.calculateLiveStats();
                }
                this.pendingSwitchSceneId = null;
                document.querySelectorAll('.scene-item').forEach(item => {
                    item.classList.toggle('active', Number(item.dataset.id) === Number(this.currentSceneId));
                });
                alert('Could not save the current scene. Scene switching was cancelled to protect your unsaved writing. Please retry once saved.');
                return;
            }

            if (this.pendingSwitchSceneId !== null && this.pendingSwitchSceneId !== targetId) {
                return;
            }

            document.querySelectorAll('.scene-item').forEach(item => {
                item.classList.toggle('active', Number(item.dataset.id) === targetId);
            });

            this.currentSceneId = targetId;
            window.history.replaceState(null, '', `?scene=${targetId}`);
            await this.loadCurrentScene();
        })();

        try {
            await this.activeSwitchPromise;
        } finally {
            this.isSwitchingScene = false;
            this.activeSwitchPromise = null;
            if (this.pendingSwitchSceneId !== null) {
                const nextTarget = this.pendingSwitchSceneId;
                this.pendingSwitchSceneId = null;
                if (nextTarget !== Number(this.currentSceneId)) {
                    await this.switchScene(nextTarget);
                }
            }
        }
    }

    // ----------------------------------------------------
    // SCENE CREATION, INSERTION, SUB-SCENE & MOVE OPERATIONS
    // ----------------------------------------------------
    async appendScene() {
        const seqState = this.detectSceneSequenceState();
        let addedEndMarker = null;

        // Auto-close active sequence if not already ended
        if (seqState.inSequence && !seqState.hasEnded) {
            const endMarkerText = seqState.type === 'montage' ? 'MONTAGE ENDS' : 'SONG ENDS';
            const allBlocks = Array.from(this.pageContainer.querySelectorAll('.script-element-block'));
            const lastBlock = allBlocks.length > 0 ? allBlocks[allBlocks.length - 1] : null;
            addedEndMarker = this.createElementBlock('shot', endMarkerText, lastBlock);
            this.renumberSequenceShots();
            this.updateSequenceToolbarState();
            this.markDirty();
            this.calculateLiveStats();
        }

        const addedTransition = this.ensurePreviousSceneHasTransition();
        try {
            await this.flushSave();
        } catch (err) {
            console.error('Save failed before appending scene:', err);
            if (addedTransition && addedTransition.parentElement) {
                addedTransition.remove();
                this.calculateLiveStats();
            }
            if (addedEndMarker && addedEndMarker.parentElement) {
                addedEndMarker.remove();
                this.updateSequenceToolbarState();
                this.calculateLiveStats();
            }
            alert('Could not save the current scene. Scene creation was cancelled to protect your unsaved writing. Please retry once saved.');
            return;
        }

        try {
            this.setSaveStatus('saving', 'Creating scene...');
            let res;
            if (seqState.isSequenceScene) {
                res = await fetch(`/scripts/api/${this.scriptId}/scenes/insert/`, {
                    method: 'POST',
                    headers: this.getHeaders(),
                    body: JSON.stringify({
                        reference_scene_id: parseInt(this.currentSceneId),
                        position: 'after',
                        heading: 'INT. LOCATION - DAY'
                    })
                });
            } else {
                res = await fetch(`/scripts/api/${this.scriptId}/scenes/create/`, {
                    method: 'POST',
                    headers: this.getHeaders(),
                    body: JSON.stringify({
                        heading: 'INT. LOCATION - DAY'
                    })
                });
            }
            if (!res.ok) throw new Error('Could not create scene');
            const data = await res.json();
            
            this.renderScenesTree(data.scenes_tree);
            await this.switchScene(data.scene.id);
        } catch (err) {
            alert('Failed to append scene: ' + err.message);
            this.setSaveStatus('error', 'Error creating scene');
        }
    }

    async addSubSceneDirect() {
        try {
            await this.flushSave();
        } catch (err) {
            console.error('Save failed before creating sub-scene:', err);
            alert('Could not save the current scene. Sub-scene creation was cancelled to protect your unsaved writing. Please retry once saved.');
            return;
        }

        try {
            this.setSaveStatus('saving', 'Creating sub-scene...');
            const parentId = this.currentMainSceneId || this.currentSceneId;
            const res = await fetch(`/scripts/api/${this.scriptId}/scenes/${parentId}/subscene/`, {
                method: 'POST',
                headers: this.getHeaders(),
                body: JSON.stringify({
                    heading: 'INT. LOCATION - CONTINUOUS'
                })
            });
            if (!res.ok) throw new Error('Could not create sub-scene');
            const data = await res.json();

            this.renderScenesTree(data.scenes_tree);
            await this.switchScene(data.scene.id);
        } catch (err) {
            alert('Failed to create sub-scene: ' + err.message);
            this.setSaveStatus('error', 'Error creating sub-scene');
        }
    }

    openInsertModal(referenceSceneId = null, position = 'after', heading = '', isSub = false) {
        const refId = referenceSceneId || this.currentSceneId;
        const defaultHeading = heading || (isSub ? 'INT. SUB LOCATION - DAY' : 'INT. LOCATION - DAY');
        const parsed = this.parseHeading(defaultHeading);

        document.getElementById('editorInsertRefId').value = refId;
        document.getElementById('editorInsertPos').value = position;
        
        const intextEl = document.getElementById('editorInsertIntext');
        if (intextEl) intextEl.value = parsed.intext;
        const locEl = document.getElementById('editorInsertLocation');
        if (locEl) locEl.value = parsed.location || (isSub ? 'SUB LOCATION' : 'LOCATION');
        const timeEl = document.getElementById('editorInsertTime');
        if (timeEl) timeEl.value = parsed.time;

        document.getElementById('editorInsertSummary').value = '';
        document.getElementById('editorInsertModalTitle').innerHTML = `<i class="bi bi-plus-circle me-1 text-primary"></i> Insert ${isSub ? 'Sub Scene' : 'Scene'} (${position.toUpperCase()})`;
        const submitBtn = document.getElementById('btnEditorSubmitInsert');
        if (submitBtn) submitBtn.innerText = `Insert ${isSub ? 'Sub Scene' : 'Scene'}`;
        
        if (this.bsOffcanvas && this.offcanvasEl && this.offcanvasEl.classList.contains('show')) {
            this.bsOffcanvas.hide();
        }
        if (this.insertModalEl) {
            const modal = bootstrap.Modal.getOrCreateInstance(this.insertModalEl);
            modal.show();
            setTimeout(() => { if (locEl) { locEl.focus(); locEl.select(); } }, 300);
        }
    }

    openSubSceneModal(parentSceneId = null, heading = '') {
        const pId = parentSceneId || this.currentSceneId;
        const defaultHeading = heading || 'INT. LOCATION - DAY';
        const parsed = this.parseHeading(defaultHeading);

        document.getElementById('editorSubSceneParentId').value = pId;

        const intextEl = document.getElementById('editorSubSceneIntext');
        if (intextEl) intextEl.value = parsed.intext;
        const locEl = document.getElementById('editorSubSceneLocation');
        if (locEl) locEl.value = parsed.location || 'LOCATION';
        const timeEl = document.getElementById('editorSubSceneTime');
        if (timeEl) timeEl.value = parsed.time;

        document.getElementById('editorSubSceneSummary').value = '';
        
        if (this.bsOffcanvas && this.offcanvasEl && this.offcanvasEl.classList.contains('show')) {
            this.bsOffcanvas.hide();
        }
        if (this.subSceneModalEl) {
            const modal = bootstrap.Modal.getOrCreateInstance(this.subSceneModalEl);
            modal.show();
            setTimeout(() => { if (locEl) { locEl.focus(); locEl.select(); } }, 300);
        }
    }

    async submitInsertScene(refId, pos, heading, summary) {
        let addedTransition = null;
        if (pos === 'after' && Number(refId) === Number(this.currentSceneId)) {
            addedTransition = this.ensurePreviousSceneHasTransition();
        }
        try {
            await this.flushSave();
        } catch (err) {
            console.error('Save failed before inserting scene:', err);
            if (addedTransition && addedTransition.parentElement) {
                addedTransition.remove();
                this.calculateLiveStats();
            }
            alert('Could not save the current scene. Scene insertion was cancelled to protect your unsaved writing. Please retry once saved.');
            return;
        }

        try {
            this.setSaveStatus('saving', 'Inserting scene...');
            const res = await fetch(`/scripts/api/${this.scriptId}/scenes/insert/`, {
                method: 'POST',
                headers: this.getHeaders(),
                body: JSON.stringify({
                    reference_scene_id: parseInt(refId),
                    position: pos,
                    heading: heading,
                    summary: summary
                })
            });
            if (!res.ok) throw new Error('Could not insert scene');
            const data = await res.json();

            if (this.bsInsertModal) this.bsInsertModal.hide();
            this.renderScenesTree(data.scenes_tree);
            await this.switchScene(data.scene.id);
        } catch (err) {
            alert('Failed to insert scene: ' + err.message);
            this.setSaveStatus('error', 'Error inserting scene');
        }
    }

    async submitSubScene(parentId, heading, summary) {
        try {
            await this.flushSave();
        } catch (err) {
            console.error('Save failed before creating sub-scene:', err);
            alert('Could not save the current scene. Sub-scene creation was cancelled to protect your unsaved writing. Please retry once saved.');
            return;
        }

        try {
            this.setSaveStatus('saving', 'Creating sub-scene...');
            const res = await fetch(`/scripts/api/${this.scriptId}/scenes/${parentId}/subscene/`, {
                method: 'POST',
                headers: this.getHeaders(),
                body: JSON.stringify({
                    heading: heading,
                    summary: summary
                })
            });
            if (!res.ok) throw new Error('Could not create sub-scene');
            const data = await res.json();

            if (this.bsSubSceneModal) this.bsSubSceneModal.hide();
            this.renderScenesTree(data.scenes_tree);
            await this.switchScene(data.scene.id);
        } catch (err) {
            alert('Failed to create sub-scene: ' + err.message);
            this.setSaveStatus('error', 'Error creating sub-scene');
        }
    }

    async moveScene(sceneId, direction) {
        try {
            await this.flushSave();
            if (this.currentSceneId) {
                const payload = this.extractScenePayload();
                this.updateReadModeScene(this.currentSceneId, payload);
            }
        } catch (err) {
            console.error('Save failed before moving scene:', err);
            alert('Could not save the current scene. Scene movement was cancelled to protect your unsaved writing. Please retry once saved.');
            return;
        }

        try {
            this.setSaveStatus('saving', 'Moving scene...');
            const res = await fetch(`/scripts/api/${this.scriptId}/scenes/${sceneId}/move/`, {
                method: 'POST',
                headers: this.getHeaders(),
                body: JSON.stringify({ direction: direction })
            });
            const data = await res.json();
            if (data.status === 'ok') {
                this.renderScenesTree(data.scenes_tree);
                if (this.editorMode !== 'read') {
                    await this.loadCurrentScene();
                } else {
                    this.setSaveStatus('saved', 'Saved ✓');
                }
            } else {
                this.setSaveStatus('saved', 'Saved ✓');
            }
        } catch (err) {
            alert('Failed to move scene: ' + err.message);
            this.setSaveStatus('error', 'Error moving scene');
        }
    }

    async duplicateScene(sceneId) {
        try {
            await this.flushSave();
        } catch (err) {
            console.error('Save failed before duplicating scene:', err);
            alert('Could not save the current scene. Scene duplication was cancelled to protect your unsaved writing. Please retry once saved.');
            return;
        }

        try {
            this.setSaveStatus('saving', 'Duplicating scene...');
            const res = await fetch(`/scripts/api/${this.scriptId}/scenes/${sceneId}/duplicate/`, {
                method: 'POST',
                headers: this.getHeaders(),
            });
            if (!res.ok) throw new Error('Could not duplicate scene');
            const data = await res.json();

            this.renderScenesTree(data.scenes_tree);
            await this.switchScene(data.scene.id);
        } catch (err) {
            alert('Failed to duplicate scene: ' + err.message);
            this.setSaveStatus('error', 'Error duplicating scene');
        }
    }

    openRenameModal(sceneId, badge = '', heading = '', isSub = false, focusOnPosition = false) {
        const sId = parseInt(sceneId);
        const treeItem = (this.scenesTree || []).find(sc => Number(sc.id) === sId);
        const currentHeading = (treeItem && treeItem.heading) || heading || (isSub ? 'INT. SUB LOCATION - DAY' : 'INT. LOCATION - DAY');
        const parsed = this.parseHeading(currentHeading);

        const idInput = document.getElementById('editorRenameSceneId');
        if (idInput) idInput.value = sId;

        const badgeText = badge.startsWith('Scene') ? badge : (badge.includes('(Duplicate') ? badge : (isSub ? badge : `Scene ${badge}`));
        const badgeEl = document.getElementById('editorRenameBadge');
        if (badgeEl) badgeEl.innerText = badgeText || (isSub ? 'Sub-Scene' : 'Scene');

        const currPreview = document.getElementById('editorRenameCurrentPreview');
        if (currPreview) currPreview.innerText = currentHeading;

        const intextEl = document.getElementById('editorRenameIntext');
        if (intextEl) intextEl.value = parsed.intext || 'INT.';

        const locEl = document.getElementById('editorRenameLocation');
        if (locEl) locEl.value = parsed.location || '';

        const timeEl = document.getElementById('editorRenameTime');
        if (timeEl) timeEl.value = parsed.time || 'DAY';

        const errEl = document.getElementById('editorRenameError');
        if (errEl) {
            errEl.classList.add('d-none');
            errEl.innerText = '';
        }

        // Configure Scene Number input for main scenes vs sub-scenes
        const numberGroupEl = document.getElementById('editorRenameNumberGroup');
        const numberLabel = document.getElementById('editorRenameNumberLabel');
        const numberPrefix = document.getElementById('editorRenameNumberPrefix');
        const numberHelp = document.getElementById('editorRenameNumberHelp');
        const numberInput = document.getElementById('editorRenameSceneNumber');
        const numberHint = document.getElementById('editorRenameTotalScenesHint');

        if (isSub) {
            if (treeItem && (treeItem.is_duplicate || treeItem.is_intercut)) {
                if (numberGroupEl) numberGroupEl.classList.add('d-none');
            } else {
                if (numberGroupEl) numberGroupEl.classList.remove('d-none');
                const parentItem = (this.scenesTree || []).find(sc => Number(sc.id) === Number(treeItem ? treeItem.parent_scene_id : null));
                const parentLabel = parentItem ? (parentItem.nav_identifier || `Scene ${parentItem.scene_number}`) : 'Parent Scene';

                // Siblings under same parent (non-duplicate, non-intercut)
                const siblings = (this.scenesTree || []).filter(sc =>
                    Number(sc.parent_scene_id) === Number(treeItem ? treeItem.parent_scene_id : null) &&
                    !sc.is_duplicate && !sc.is_intercut
                );
                const totalSiblings = siblings.length || 1;
                const currentSiblingPos = Math.max(1, siblings.findIndex(s => Number(s.id) === sId) + 1);

                if (numberLabel) numberLabel.innerText = `Sub-Scene Position (under ${parentLabel})`;
                if (numberPrefix) numberPrefix.innerText = 'Position';
                if (numberHelp) numberHelp.innerText = `Changing position moves this sub-scene among its siblings (A, B, C...). Parent scene ${parentItem ? parentItem.scene_number : ''} remains unchanged.`;
                if (numberInput) {
                    numberInput.value = currentSiblingPos;
                    numberInput.dataset.originalPosition = currentSiblingPos;
                    numberInput.min = 1;
                    numberInput.max = totalSiblings;
                }
                if (numberHint) {
                    numberHint.innerText = totalSiblings > 0 ? `(1 to ${totalSiblings})` : '';
                }
            }
        } else {
            if (numberGroupEl) numberGroupEl.classList.remove('d-none');
            const baseMainScenes = (this.scenesTree || []).filter(sc => !sc.is_sub_scene && !sc.is_intercut && !sc.is_duplicate);
            const totalMainCount = baseMainScenes.length;
            const currentMainNum = (treeItem && treeItem.scene_number) ? treeItem.scene_number : 1;
            if (numberLabel) numberLabel.innerText = 'Scene Number / Position';
            if (numberPrefix) numberPrefix.innerText = 'Scene';
            if (numberHelp) numberHelp.innerText = 'Changing the scene number moves this scene and automatically renumbers all affected main scenes.';
            if (numberInput) {
                numberInput.value = currentMainNum;
                numberInput.dataset.originalPosition = currentMainNum;
                numberInput.min = 1;
                numberInput.max = totalMainCount || 1;
            }
            if (numberHint) {
                numberHint.innerText = totalMainCount > 0 ? `(1 to ${totalMainCount})` : '';
            }
        }

        const previewEl = document.getElementById('editorRenameFullPreview');
        const updatePreview = () => {
            let locVal = locEl ? locEl.value.trim() : '';
            if (/^(?:INT|EXT)\.?\s+/i.test(locVal)) {
                const p = this.parseHeading(locVal);
                if (intextEl) intextEl.value = p.intext;
                if (locEl) locEl.value = p.location;
                if (timeEl) timeEl.value = p.time;
                locVal = p.location;
            }
            const intextVal = intextEl ? intextEl.value : 'INT.';
            const timeVal = timeEl ? timeEl.value : 'DAY';
            const built = this.buildHeading(intextVal, locVal, timeVal);
            if (previewEl) {
                previewEl.innerText = built || `${intextVal} ${locVal || 'LOCATION'} - ${timeVal}`;
            }
        };

        if (locEl) locEl.oninput = updatePreview;
        if (intextEl) intextEl.onchange = updatePreview;
        if (timeEl) timeEl.onchange = updatePreview;
        updatePreview();

        const submitBtn = document.getElementById('btnEditorSubmitRename');
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="bi bi-check2 me-1"></i>Save';
        }

        if (this.bsOffcanvas && this.offcanvasEl && this.offcanvasEl.classList.contains('show')) {
            this.bsOffcanvas.hide();
        }
        if (this.renameModalEl) {
            const modal = bootstrap.Modal.getOrCreateInstance(this.renameModalEl);
            modal.show();
            setTimeout(() => {
                if (focusOnPosition && numberInput) {
                    numberInput.focus();
                    numberInput.select();
                } else if (locEl) {
                    locEl.focus();
                    locEl.select();
                }
            }, 300);
        }
    }

    async submitRenameScene(sceneId, newHeading, requestedSceneNum = null) {
        const targetSceneId = parseInt(sceneId);
        const submitBtn = document.getElementById('btnEditorSubmitRename');
        const cancelBtn = document.getElementById('btnEditorCancelRename');
        const errEl = document.getElementById('editorRenameError');

        if (!newHeading || !newHeading.trim()) {
            if (errEl) {
                errEl.innerText = 'Please enter a valid scene location or heading.';
                errEl.classList.remove('d-none');
            }
            return false;
        }

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Saving...';
        }
        if (cancelBtn) cancelBtn.disabled = true;

        const isActiveScene = (Number(this.currentSceneId) === targetSceneId);

        const payload = { heading: newHeading.trim() };
        if (requestedSceneNum !== null && !isNaN(requestedSceneNum)) {
            payload.scene_number = parseInt(requestedSceneNum, 10);
        }
        if (isActiveScene) {
            const activePayload = this.extractScenePayload();
            payload.elements = activePayload.elements;
            if (activePayload.summary !== undefined) payload.summary = activePayload.summary;
            if (activePayload.transition !== undefined) payload.transition = activePayload.transition;
        }

        try {
            this.setSaveStatus('saving', 'Saving scene name...');
            const res = await fetch(`/scripts/api/${this.scriptId}/scenes/${targetSceneId}/save/`, {
                method: 'POST',
                headers: this.getHeaders(),
                body: JSON.stringify(payload)
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.message || `Server returned HTTP ${res.status}`);
            }

            const result = await res.json();
            if (result.status !== 'ok') {
                throw new Error(result.message || 'Failed to rename scene.');
            }

            // Synchronize authoritative scene tree if provided by server
            if (result.scenes_tree && Array.isArray(result.scenes_tree)) {
                this.renderScenesTree(result.scenes_tree);
            } else {
                // Synchronize in-memory tree fallback
                const treeItem = (this.scenesTree || []).find(sc => Number(sc.id) === targetSceneId);
                if (treeItem) {
                    if (result.clean_location) treeItem.clean_location = result.clean_location;
                    if (result.clean_heading) treeItem.clean_heading = result.clean_heading;
                    if (result.heading) treeItem.heading = result.heading;
                    if (result.full_display_heading) treeItem.full_display_heading = result.full_display_heading;
                    if (result.scene_identifier) treeItem.scene_identifier = result.scene_identifier;
                    if (result.nav_identifier) treeItem.nav_identifier = result.nav_identifier;
                    if (result.scene_number) treeItem.scene_number = result.scene_number;
                }

                // Synchronize desktop & mobile cards
                const activeSidebarLocs = document.querySelectorAll(`.scene-item[data-id="${targetSceneId}"] .scene-nav-location`);
                activeSidebarLocs.forEach(item => {
                    item.innerText = result.clean_location || 'Location';
                    item.title = result.clean_location || 'Location';
                });

                const sceneCards = document.querySelectorAll(`.scene-item[data-id="${targetSceneId}"]`);
                sceneCards.forEach(card => {
                    card.querySelectorAll('.btn-action-insert-before, .btn-action-insert-after, .btn-action-add-sub, .btn-action-delete, .btn-action-rename').forEach(btn => {
                        btn.dataset.heading = result.heading || newHeading;
                    });
                });
            }

            // If active scene, synchronize canvas heading block and selector badge
            if (isActiveScene) {
                this.currentSceneNumber = result.scene_number || this.currentSceneNumber;
                this.currentSceneIdentifier = result.scene_identifier || this.currentSceneIdentifier;
                this.currentFullHeading = result.full_display_heading || `${result.nav_identifier || this.currentSceneIdentifier} : ${result.clean_heading || newHeading}`;
                if (this.currentSelectorBadge) {
                    this.currentSelectorBadge.innerText = this.currentFullHeading;
                }

                if (this.pageContainer) {
                    const parsed = this.parseHeading(result.heading || newHeading);
                    const canvasLoc = this.pageContainer.querySelector('.heading-location-input');
                    if (canvasLoc) canvasLoc.value = parsed.location;
                    const canvasIntext = this.pageContainer.querySelector('.heading-intext-select');
                    if (canvasIntext) canvasIntext.value = parsed.intext;
                    const canvasTime = this.pageContainer.querySelector('.heading-time-select');
                    if (canvasTime) canvasTime.value = parsed.time;
                    const canvasEditable = this.pageContainer.querySelector('.script-element-block[data-type="scene_heading"] .element-content');
                    if (canvasEditable) canvasEditable.innerText = result.heading || newHeading;
                }

                this.isDirty = false;
                this.setSaveStatus('saved', 'Saved ✓');
            } else {
                this.setSaveStatus('saved', 'Renamed ✓');
            }

            if (result.script_stats) {
                this.updateStats(result.script_stats);
            }

            // Close modal on success if position is not also being changed
            if (this.renameModalEl && !requestedSceneNum && !document.getElementById('editorRenameForm')?.dataset?.isChainedReorder) {
                const modal = bootstrap.Modal.getInstance(this.renameModalEl);
                if (modal) modal.hide();
            }

            return true;
        } catch (err) {
            console.error('Rename failed:', err);
            this.setSaveStatus('error', 'Rename failed');
            if (errEl) {
                errEl.innerText = err.message || 'Failed to rename scene. Please check your connection and retry.';
                errEl.classList.remove('d-none');
            }
            return false;
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<i class="bi bi-check2 me-1"></i>Save';
            }
            if (cancelBtn) cancelBtn.disabled = false;
        }
    }

    openPromoteModal(sceneId, badge = '', heading = '', isDup = false, isIntercut = false) {
        if (isDup) {
            alert('Duplicate sub-scenes retain their base sub-scene identity and cannot be promoted to a main scene directly.');
            return;
        }
        if (isIntercut) {
            alert('Intercut sub-scenes retain their source scene link and cannot be promoted to a main scene.');
            return;
        }

        const sId = parseInt(sceneId);
        const idInput = document.getElementById('editorPromoteSceneId');
        if (idInput) idInput.value = sId;

        const badgeEl = document.getElementById('editorPromoteBadge');
        if (badgeEl) badgeEl.innerText = badge || 'Sub-Scene';

        const previewEl = document.getElementById('editorPromotePreview');
        if (previewEl) previewEl.innerText = heading || 'INT. LOCATION - DAY';

        const errEl = document.getElementById('editorPromoteError');
        if (errEl) {
            errEl.classList.add('d-none');
            errEl.innerText = '';
        }

        const confirmBtn = document.getElementById('btnEditorConfirmPromote');
        if (confirmBtn) {
            confirmBtn.disabled = false;
            confirmBtn.innerHTML = '<i class="bi bi-box-arrow-up-right me-1"></i> Promote to Main Scene';
        }

        if (this.bsOffcanvas && this.offcanvasEl && this.offcanvasEl.classList.contains('show')) {
            this.bsOffcanvas.hide();
        }
        if (this.promoteModalEl) {
            const modal = bootstrap.Modal.getOrCreateInstance(this.promoteModalEl);
            modal.show();
        }
    }

    async confirmPromoteSubScene(sceneId) {
        const sId = parseInt(sceneId);
        const confirmBtn = document.getElementById('btnEditorConfirmPromote');
        const cancelBtn = document.getElementById('btnEditorCancelPromote');
        const errEl = document.getElementById('editorPromoteError');

        if (confirmBtn) {
            confirmBtn.disabled = true;
            confirmBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Promoting...';
        }
        if (cancelBtn) cancelBtn.disabled = true;

        // 1. If promoting the active scene and there are pending changes or a save is in flight, flush save first
        const isActiveScene = (Number(this.currentSceneId) === sId);
        if (isActiveScene && (this.isDirty || this.isSaving)) {
            try {
                this.setSaveStatus('saving', 'Saving scene before promotion...');
                await this.flushSave();
                if (this.isDirty) {
                    throw new Error('Unsaved changes could not be saved before promotion.');
                }
            } catch (saveErr) {
                console.error('Save failed before promotion:', saveErr);
                if (errEl) {
                    errEl.innerText = 'Could not save current changes before promotion. Please retry once saved.';
                    errEl.classList.remove('d-none');
                }
                this.setSaveStatus('error', 'Save failed before promotion');
                if (confirmBtn) {
                    confirmBtn.disabled = false;
                    confirmBtn.innerHTML = '<i class="bi bi-box-arrow-up-right me-1"></i> Promote to Main Scene';
                }
                if (cancelBtn) cancelBtn.disabled = false;
                return;
            }
        }

        try {
            this.setSaveStatus('saving', 'Promoting scene...');
            const res = await fetch(`/scripts/api/${this.scriptId}/scenes/${sId}/promote/`, {
                method: 'POST',
                headers: this.getHeaders()
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.message || `Server returned HTTP ${res.status}`);
            }

            const result = await res.json();
            if (result.status !== 'ok') {
                throw new Error(result.message || 'Failed to promote sub-scene.');
            }

            if (this.promoteModalEl) {
                const modal = bootstrap.Modal.getInstance(this.promoteModalEl);
                if (modal) modal.hide();
            }

            if (result.scenes_tree && Array.isArray(result.scenes_tree)) {
                this.renderScenesTree(result.scenes_tree);
            }

            // If active scene was the promoted scene, update state
            const isActiveScene = (Number(this.currentSceneId) === sId);
            if (isActiveScene && result.scene) {
                this.currentSceneIsSub = false;
                this.currentSceneNumber = result.scene.scene_number || this.currentSceneNumber;
                this.currentSceneIdentifier = result.scene.scene_identifier || this.currentSceneIdentifier;
                this.currentFullHeading = result.scene.full_display_heading || `${result.scene.nav_identifier || this.currentSceneIdentifier} : ${result.scene.clean_heading || ''}`;
                if (this.currentSelectorBadge) {
                    this.currentSelectorBadge.innerText = this.currentFullHeading;
                }
            }

            this.setSaveStatus('saved', 'Saved ✓');
        } catch (err) {
            console.error('Promotion failed:', err);
            if (errEl) {
                errEl.innerText = err.message || 'Failed to promote sub-scene.';
                errEl.classList.remove('d-none');
            }
            this.setSaveStatus('error', 'Error promoting scene');
            if (confirmBtn) {
                confirmBtn.disabled = false;
                confirmBtn.innerHTML = '<i class="bi bi-box-arrow-up-right me-1"></i> Promote to Main Scene';
            }
            if (cancelBtn) cancelBtn.disabled = false;
        }
    }

    async submitReorderSubScene(sceneId, targetPosition) {
        const sId = parseInt(sceneId);
        const targetPos = parseInt(targetPosition, 10);
        const submitBtn = document.getElementById('btnEditorSubmitRename');
        const cancelBtn = document.getElementById('btnEditorCancelRename');
        const errEl = document.getElementById('editorRenameError');

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Moving...';
        }
        if (cancelBtn) cancelBtn.disabled = true;

        try {
            this.setSaveStatus('saving', 'Moving sub-scene...');
            const res = await fetch(`/scripts/api/${this.scriptId}/scenes/${sId}/reorder-sub/`, {
                method: 'POST',
                headers: this.getHeaders(),
                body: JSON.stringify({ target_position: targetPos })
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.message || `Server returned HTTP ${res.status}`);
            }

            const result = await res.json();
            if (result.status !== 'ok' && result.status !== 'noop') {
                throw new Error(result.message || 'Failed to reorder sub-scene.');
            }

            if (this.renameModalEl) {
                const modal = bootstrap.Modal.getInstance(this.renameModalEl);
                if (modal) modal.hide();
            }

            if (result.scenes_tree && Array.isArray(result.scenes_tree)) {
                this.renderScenesTree(result.scenes_tree);
            }

            // If active scene, synchronize
            const isActiveScene = (Number(this.currentSceneId) === sId);
            if (isActiveScene && result.scene) {
                this.currentSceneNumber = result.scene.scene_number || this.currentSceneNumber;
                this.currentSceneIdentifier = result.scene.scene_identifier || this.currentSceneIdentifier;
                this.currentFullHeading = result.scene.full_display_heading || `${result.scene.nav_identifier || this.currentSceneIdentifier} : ${result.scene.clean_heading || ''}`;
                if (this.currentSelectorBadge) {
                    this.currentSelectorBadge.innerText = this.currentFullHeading;
                }
            }

            this.setSaveStatus('saved', 'Saved ✓');
        } catch (err) {
            console.error('Reorder sub-scene failed:', err);
            if (errEl) {
                errEl.innerText = err.message || 'Failed to reorder sub-scene.';
                errEl.classList.remove('d-none');
            }
            this.setSaveStatus('error', 'Error moving sub-scene');
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<i class="bi bi-check2 me-1"></i>Save';
            }
            if (cancelBtn) cancelBtn.disabled = false;
        }
    }

    openDeleteModal(sceneId, badge = '', heading = '', isSub = false) {
        this.pendingDeleteSceneId = sceneId;
        const badgeText = badge.startsWith('Scene') ? badge : (badge.includes('(Duplicate') ? badge : `Scene ${badge}`);

        const badgeEl = document.getElementById('editorDeleteBadge');
        if (badgeEl) badgeEl.innerText = badgeText;

        const headingEl = document.getElementById('editorDeleteHeading');
        if (headingEl) headingEl.innerText = heading || 'UNTITLED SCENE';

        const warningEl = document.getElementById('editorDeleteWarning');
        if (warningEl) {
            warningEl.innerText = isSub
                ? 'This will move this sub-scene to Trash. It can be restored later.'
                : 'This will move this scene and all of its sub-scenes to Trash. They can be restored later.';
        }

        const submitBtnText = document.getElementById('btnEditorSubmitDeleteText');
        if (submitBtnText) submitBtnText.innerText = 'Move to Trash';

        if (this.bsOffcanvas && this.offcanvasEl && this.offcanvasEl.classList.contains('show')) {
            this.bsOffcanvas.hide();
        }
        if (this.deleteModalEl) {
            const modal = bootstrap.Modal.getOrCreateInstance(this.deleteModalEl);
            modal.show();
        }
    }

    async submitDeleteScene() {
        if (!this.pendingDeleteSceneId) return;
        const sceneId = this.pendingDeleteSceneId;
        const submitBtn = document.getElementById('btnEditorSubmitDelete');
        const submitBtnText = document.getElementById('btnEditorSubmitDeleteText');

        if (submitBtn) submitBtn.disabled = true;
        if (submitBtnText) submitBtnText.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Moving to Trash...';

        try {
            await this.flushSave();
            if (this.currentSceneId && Number(this.currentSceneId) !== Number(sceneId)) {
                const payload = this.extractScenePayload();
                this.updateReadModeScene(this.currentSceneId, payload);
            }
        } catch (err) {
            console.error('Save failed before deleting scene:', err);
            if (submitBtn) submitBtn.disabled = false;
            if (submitBtnText) submitBtnText.innerText = 'Move to Trash';
            alert('Could not save the current scene. Scene deletion was cancelled to protect your unsaved writing. Please retry once saved.');
            return;
        }

        try {
            this.setSaveStatus('saving', 'Moving scene to Trash...');
            const res = await fetch(`/scripts/api/${this.scriptId}/scenes/${sceneId}/delete/`, {
                method: 'POST',
                headers: this.getHeaders(),
            });
            const data = await res.json();
            if (!res.ok || data.status !== 'ok') {
                alert(data.message || 'Cannot move scene to Trash');
                this.setSaveStatus('saved', 'Saved ✓');
                if (submitBtn) submitBtn.disabled = false;
                if (submitBtnText) submitBtnText.innerText = 'Move to Trash';
                return;
            }

            if (this.deleteModalEl) {
                const modal = bootstrap.Modal.getOrCreateInstance(this.deleteModalEl);
                modal.hide();
            }

            this.renderScenesTree(data.scenes_tree);
            // Refresh trash count badge immediately
            this.fetchSceneTrashCount();

            if (Number(sceneId) === Number(this.currentSceneId) && data.fallback_scene_id) {
                if (this.editorMode === 'read') {
                    this.currentSceneId = Number(data.fallback_scene_id);
                    const targetEl = document.getElementById(`read-scene-${data.fallback_scene_id}`);
                    if (targetEl) targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
                } else {
                    await this.switchScene(data.fallback_scene_id);
                }
            } else if (this.editorMode !== 'read') {
                await this.loadCurrentScene();
            }
        } catch (err) {
            alert('Failed to move scene to Trash: ' + err.message);
            this.setSaveStatus('error', 'Error moving scene to Trash');
        } finally {
            if (submitBtn) submitBtn.disabled = false;
            if (submitBtnText) submitBtnText.innerText = 'Move to Trash';
            this.pendingDeleteSceneId = null;
        }
    }

    // ----------------------------------------------------
    // MODAL & BUTTON BINDINGS
    // ----------------------------------------------------
    bindSceneModals() {
        // Delete Confirm Button Handler
        const btnDeleteSubmit = document.getElementById('btnEditorSubmitDelete');
        if (btnDeleteSubmit) {
            btnDeleteSubmit.addEventListener('click', () => {
                this.submitDeleteScene();
            });
        }
        // Insert Form Submit
        const insertForm = document.getElementById('editorInsertForm');
        if (insertForm) {
            insertForm.addEventListener('submit', (e) => {
                e.preventDefault();
                const refId = document.getElementById('editorInsertRefId').value;
                const pos = document.getElementById('editorInsertPos').value;
                const intextEl = document.getElementById('editorInsertIntext');
                const locEl = document.getElementById('editorInsertLocation');
                const timeEl = document.getElementById('editorInsertTime');

                const intext = intextEl ? intextEl.value : 'INT.';
                const loc = locEl ? locEl.value.trim() : '';
                const time = timeEl ? timeEl.value : 'DAY';

                if (!loc) {
                    alert('Please enter a scene location.');
                    if (locEl) locEl.focus();
                    return;
                }

                const heading = this.buildHeading(intext, loc, time);
                const summary = document.getElementById('editorInsertSummary').value.trim();
                this.submitInsertScene(refId, pos, heading, summary);
            });
        }

        // Sub Scene Form Submit
        const subSceneForm = document.getElementById('editorSubSceneForm');
        if (subSceneForm) {
            subSceneForm.addEventListener('submit', (e) => {
                e.preventDefault();
                const parentId = document.getElementById('editorSubSceneParentId').value;
                const intextEl = document.getElementById('editorSubSceneIntext');
                const locEl = document.getElementById('editorSubSceneLocation');
                const timeEl = document.getElementById('editorSubSceneTime');

                const intext = intextEl ? intextEl.value : 'INT.';
                const loc = locEl ? locEl.value.trim() : '';
                const time = timeEl ? timeEl.value : 'DAY';

                if (!loc) {
                    alert('Please enter a scene location.');
                    if (locEl) locEl.focus();
                    return;
                }

                const heading = this.buildHeading(intext, loc, time);
                const summary = document.getElementById('editorSubSceneSummary').value.trim();
                this.submitSubScene(parentId, heading, summary);
            });
        }

        // Promote Sub-Scene Confirm
        const btnPromoteConfirm = document.getElementById('btnEditorConfirmPromote');
        if (btnPromoteConfirm) {
            btnPromoteConfirm.addEventListener('click', () => {
                const sceneId = document.getElementById('editorPromoteSceneId').value;
                if (sceneId) {
                    this.confirmPromoteSubScene(sceneId);
                }
            });
        }

        // Rename Scene Form Submit
        const renameForm = document.getElementById('editorRenameForm');
        if (renameForm) {
            renameForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const sceneId = document.getElementById('editorRenameSceneId').value;
                const intextEl = document.getElementById('editorRenameIntext');
                const locEl = document.getElementById('editorRenameLocation');
                const timeEl = document.getElementById('editorRenameTime');
                const errEl = document.getElementById('editorRenameError');

                const intext = intextEl ? intextEl.value : 'INT.';
                const loc = locEl ? locEl.value.trim() : '';
                const time = timeEl ? timeEl.value : 'DAY';

                if (!loc) {
                    if (errEl) {
                        errEl.innerText = 'Please enter a scene location.';
                        errEl.classList.remove('d-none');
                    }
                    if (locEl) locEl.focus();
                    return;
                }

                const treeItem = (this.scenesTree || []).find(sc => Number(sc.id) === Number(sceneId));
                const isSub = treeItem ? Boolean(treeItem.is_sub_scene) : false;
                const numberInput = document.getElementById('editorRenameSceneNumber');

                if (isSub) {
                    let requestedSubPos = null;
                    let originalSubPos = null;
                    if (numberInput && !numberInput.closest('#editorRenameNumberGroup').classList.contains('d-none')) {
                        const numValStr = numberInput.value.trim();
                        originalSubPos = numberInput.dataset.originalPosition ? parseInt(numberInput.dataset.originalPosition, 10) : null;
                        if (!numValStr || isNaN(numValStr) || !Number.isInteger(Number(numValStr))) {
                            if (errEl) {
                                errEl.innerText = 'Please enter a valid positive whole number for the sub-scene position.';
                                errEl.classList.remove('d-none');
                            }
                            numberInput.focus();
                            return;
                        }
                        const numVal = parseInt(numValStr, 10);
                        if (numVal <= 0) {
                            if (errEl) {
                                errEl.innerText = 'Sub-scene position must be a positive integer greater than zero.';
                                errEl.classList.remove('d-none');
                            }
                            numberInput.focus();
                            return;
                        }
                        const maxPos = parseInt(numberInput.max, 10) || 1;
                        if (numVal > maxPos) {
                            if (errEl) {
                                errEl.innerText = `Sub-scene position cannot exceed the total number of sibling sub-scenes (${maxPos}).`;
                                errEl.classList.remove('d-none');
                            }
                            numberInput.focus();
                            return;
                        }
                        requestedSubPos = numVal;
                    }

                    const newHeading = this.buildHeading(intext, loc, time);
                    const currentHeading = (treeItem && treeItem.heading) || '';
                    const headingChanged = (newHeading.trim() !== currentHeading.trim());
                    const positionChanged = (requestedSubPos !== null && originalSubPos !== null && requestedSubPos !== originalSubPos);

                    if (positionChanged && !headingChanged) {
                        await this.submitReorderSubScene(sceneId, requestedSubPos);
                    } else if (positionChanged && headingChanged) {
                        renameForm.dataset.isChainedReorder = 'true';
                        let renameOk = false;
                        try {
                            renameOk = await this.submitRenameScene(sceneId, newHeading, null);
                        } finally {
                            delete renameForm.dataset.isChainedReorder;
                        }
                        if (renameOk) {
                            await this.submitReorderSubScene(sceneId, requestedSubPos);
                        }
                    } else {
                        await this.submitRenameScene(sceneId, newHeading, null);
                    }
                } else {
                    let requestedSceneNum = null;
                    if (numberInput) {
                        const numValStr = numberInput.value.trim();
                        if (!numValStr || isNaN(numValStr) || !Number.isInteger(Number(numValStr))) {
                            if (errEl) {
                                errEl.innerText = 'Please enter a valid positive whole number for the scene.';
                                errEl.classList.remove('d-none');
                            }
                            numberInput.focus();
                            return;
                        }
                        const numVal = parseInt(numValStr, 10);
                        if (numVal <= 0) {
                            if (errEl) {
                                errEl.innerText = 'Scene number must be a positive integer greater than zero.';
                                errEl.classList.remove('d-none');
                            }
                            numberInput.focus();
                            return;
                        }
                        const baseMainCount = (this.scenesTree || []).filter(sc => !sc.is_sub_scene && !sc.is_intercut && !sc.is_duplicate).length;
                        if (baseMainCount > 0 && numVal > baseMainCount) {
                            if (errEl) {
                                errEl.innerText = `Scene number cannot exceed the total number of main scenes (${baseMainCount}).`;
                                errEl.classList.remove('d-none');
                            }
                            numberInput.focus();
                            return;
                        }
                        requestedSceneNum = numVal;
                    }

                    const heading = this.buildHeading(intext, loc, time);
                    this.submitRenameScene(sceneId, heading, requestedSceneNum);
                }
            });
        }

        // Offcanvas quick buttons
        const btnOffcanvasAdd = document.getElementById('btnOffcanvasAddScene');
        if (btnOffcanvasAdd) {
            btnOffcanvasAdd.addEventListener('click', async () => {
                if (this.bsOffcanvas) this.bsOffcanvas.hide();
                await this.appendScene();
            });
        }
        const btnOffcanvasInsert = document.getElementById('btnOffcanvasInsertScene');
        if (btnOffcanvasInsert) {
            btnOffcanvasInsert.addEventListener('click', () => {
                this.openInsertModal(this.currentSceneId, 'after', '', this.currentSceneIsSub);
            });
        }
        const btnOffcanvasSub = document.getElementById('btnOffcanvasSubScene');
        if (btnOffcanvasSub) {
            btnOffcanvasSub.addEventListener('click', () => {
                this.openSubSceneModal(this.currentSceneId);
            });
        }

        // Sidebar quick buttons
        const btnAddScene = document.getElementById('btnAddScene');
        if (btnAddScene) {
            btnAddScene.addEventListener('click', async () => {
                await this.appendScene();
            });
        }
        const btnSidebarInsert = document.getElementById('btnSidebarInsertScene');
        if (btnSidebarInsert) {
            btnSidebarInsert.addEventListener('click', () => {
                this.openInsertModal(this.currentSceneId, 'after', '', this.currentSceneIsSub);
            });
        }
        const btnSidebarSub = document.getElementById('btnSidebarSubScene');
        if (btnSidebarSub) {
            btnSidebarSub.addEventListener('click', () => {
                this.openSubSceneModal(this.currentSceneId);
            });
        }

        // Toolbar Quick Scene Dropdown items
        const btnTbAppend = document.getElementById('btnToolbarAppendScene');
        if (btnTbAppend) btnTbAppend.addEventListener('click', () => this.appendScene());

        const btnTbInsertBefore = document.getElementById('btnToolbarInsertBefore');
        if (btnTbInsertBefore) btnTbInsertBefore.addEventListener('click', () => this.openInsertModal(this.currentSceneId, 'before', '', this.currentSceneIsSub));

        const btnTbInsertAfter = document.getElementById('btnToolbarInsertAfter');
        if (btnTbInsertAfter) btnTbInsertAfter.addEventListener('click', () => this.openInsertModal(this.currentSceneId, 'after', '', this.currentSceneIsSub));

        const btnTbSub = document.getElementById('btnToolbarAddSubScene');
        if (btnTbSub) btnTbSub.addEventListener('click', () => this.openSubSceneModal(this.currentSceneId));
    }

    // ----------------------------------------------------
    // SCENE TRASH (BATCH 3D-D)
    // ----------------------------------------------------
    bindSceneTrashEvents() {
        // Any button with .btn-open-scene-trash or #btnTopOpenSceneTrash / #btnNavOpenSceneTrash
        document.querySelectorAll('.btn-open-scene-trash').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                this.openSceneTrashModal();
            });
        });

        const retryBtn = document.getElementById('btnRetryLoadTrash');
        if (retryBtn) {
            retryBtn.addEventListener('click', () => {
                this.openSceneTrashModal();
            });
        }
    }

    async fetchSceneTrashCount() {
        try {
            const res = await fetch(`/scripts/api/${this.scriptId}/trash/scenes/`, {
                headers: this.getHeaders()
            });
            if (!res.ok) return;
            const data = await res.json();
            if (data.status === 'ok') {
                const count = data.total_trashed !== undefined ? data.total_trashed : (data.trashed_scenes ? data.trashed_scenes.length : 0);
                this.updateTrashCountBadges(count);
            }
        } catch (e) {
            console.error('Failed to fetch Scene Trash count:', e);
        }
    }

    updateTrashCountBadges(count) {
        document.querySelectorAll('.scene-trash-count').forEach(el => {
            el.innerText = count;
        });
        const modalBadge = document.getElementById('sceneTrashModalCountBadge');
        if (modalBadge) {
            modalBadge.innerText = count;
        }
    }

    async openSceneTrashModal() {
        if (!this.trashModalEl) return;
        const modal = bootstrap.Modal.getOrCreateInstance(this.trashModalEl);
        modal.show();

        const loadingEl = document.getElementById('sceneTrashLoadingState');
        const emptyEl = document.getElementById('sceneTrashEmptyState');
        const errorEl = document.getElementById('sceneTrashErrorState');
        const listEl = document.getElementById('sceneTrashList');
        const alertArea = document.getElementById('sceneTrashAlertArea');
        const statsEl = document.getElementById('sceneTrashFooterStats');

        if (loadingEl) loadingEl.style.display = 'block';
        if (emptyEl) emptyEl.style.display = 'none';
        if (errorEl) errorEl.style.display = 'none';
        if (listEl) {
            listEl.style.display = 'none';
            listEl.innerHTML = '';
        }
        if (alertArea) {
            alertArea.style.display = 'none';
            alertArea.innerHTML = '';
        }
        if (statsEl) statsEl.innerText = '';

        try {
            const res = await fetch(`/scripts/api/${this.scriptId}/trash/scenes/`, {
                headers: this.getHeaders()
            });

            if (!res.ok) {
                let errText = 'Failed to load Scene Trash (HTTP ' + res.status + ')';
                try {
                    const errData = await res.json();
                    if (errData.message) errText = errData.message;
                } catch (_) {}
                throw new Error(errText);
            }

            const data = await res.json();
            if (data.status !== 'ok') {
                throw new Error(data.message || 'Error loading trashed scenes');
            }

            if (loadingEl) loadingEl.style.display = 'none';
            const trashedScenes = data.trashed_scenes || [];
            this.updateTrashCountBadges(trashedScenes.length);

            if (trashedScenes.length === 0) {
                if (emptyEl) emptyEl.style.display = 'block';
                if (statsEl) statsEl.innerText = '0 scenes in Trash';
            } else {
                if (listEl) {
                    listEl.style.display = 'flex';
                    this.renderTrashItems(trashedScenes);
                }
                if (statsEl) {
                    statsEl.innerText = `${trashedScenes.length} trashed scene${trashedScenes.length === 1 ? '' : 's'}`;
                }
            }
        } catch (err) {
            if (loadingEl) loadingEl.style.display = 'none';
            if (errorEl) {
                errorEl.style.display = 'block';
                const msgEl = document.getElementById('sceneTrashErrorMessage');
                if (msgEl) msgEl.innerText = err.message || 'Failed to load Scene Trash.';
            }
        }
    }

    renderTrashItems(trashedScenes) {
        const listEl = document.getElementById('sceneTrashList');
        if (!listEl) return;

        // Collect all active main scenes from current screenplay for the parent dropdown
        const activeMainScenes = [];
        if (Array.isArray(this.scenesTree)) {
            this.scenesTree.forEach(s => {
                if (!s.is_sub_scene) {
                    activeMainScenes.push({
                        id: s.id,
                        number: s.display_number || s.nav_identifier || `Scene ${s.order}`,
                        heading: s.clean_heading || s.heading || 'UNTITLED SCENE'
                    });
                }
            });
        }

        const escapeHtml = (str) => {
            if (str === null || str === undefined) return '';
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        };

        const itemsHtml = trashedScenes.map(sc => {
            const isSub = Boolean(sc.is_sub_scene);
            const isIntercut = Boolean(sc.is_intercut);
            const parentStatus = sc.parent_status; // 'active', 'trashed', 'missing', or null
            const intercutStatus = sc.intercut_source_status; // 'active', 'trashed', 'missing', or null

            // Badge for Scene Number / Identifier
            let sceneDisplay = 'Scene number unavailable';
            if (sc.scene_number && String(sc.scene_number).trim() !== '' && String(sc.scene_number).trim() !== '0' && String(sc.scene_number).trim() !== 'Scene 0') {
                const rawNum = String(sc.scene_number).trim();
                sceneDisplay = rawNum.startsWith('Scene ') ? rawNum : `Scene ${rawNum}`;
            }
            const sceneBadge = `<span class="badge bg-secondary-subtle text-dark border font-screenplay fs-6 px-2 py-1">${escapeHtml(sceneDisplay)}</span>`;

            // Type Badges
            let typeBadges = '';
            if (isSub) {
                typeBadges += `<span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle me-1"><i class="bi bi-diagram-3 me-1"></i>Sub-scene</span>`;
            } else {
                typeBadges += `<span class="badge bg-primary-subtle text-primary border border-primary-subtle me-1"><i class="bi bi-camera-video me-1"></i>Main Scene</span>`;
            }

            if (isIntercut) {
                let intercutBadgeClass = 'bg-info-subtle text-info border-info-subtle';
                let intercutStatusText = 'Intercut';
                if (intercutStatus === 'active') {
                    intercutStatusText = 'Intercut (Source Active)';
                } else if (intercutStatus === 'trashed') {
                    intercutBadgeClass = 'bg-danger-subtle text-danger border-danger-subtle';
                    intercutStatusText = 'Intercut (Source Trashed)';
                } else if (intercutStatus === 'missing') {
                    intercutBadgeClass = 'bg-secondary-subtle text-secondary border-secondary-subtle';
                    intercutStatusText = 'Intercut (Source Missing)';
                }
                typeBadges += `<span class="badge ${intercutBadgeClass} border me-1"><i class="bi bi-arrow-left-right me-1"></i>${escapeHtml(intercutStatusText)}</span>`;
            }

            // Parent status info
            let parentInfoHtml = '';
            let requiresParentChoice = false;

            if (isSub) {
                const parentNumDisplay = sc.original_parent_scene_number ? `Scene ${sc.original_parent_scene_number}` : '';
                if (parentStatus === 'active') {
                    const parentDisplay = parentNumDisplay || 'Original Parent';
                    parentInfoHtml = `<div class="small text-muted mt-1 d-flex align-items-center gap-1"><i class="bi bi-link-45deg text-success"></i> Parent: <span class="badge bg-success-subtle text-success border border-success-subtle">${escapeHtml(parentDisplay)} (Active)</span></div>`;
                } else if (parentStatus === 'trashed') {
                    requiresParentChoice = true;
                    const parentLabel = parentNumDisplay ? ` (${parentNumDisplay})` : '';
                    parentInfoHtml = `<div class="small text-danger mt-1 d-flex align-items-center gap-1"><i class="bi bi-exclamation-triangle-fill text-warning"></i> Original parent${escapeHtml(parentLabel)} is in Trash. Restoration requires selecting how to restore.</div>`;
                } else {
                    requiresParentChoice = true;
                    const parentLabel = parentNumDisplay ? ` (${parentNumDisplay})` : '';
                    parentInfoHtml = `<div class="small text-muted mt-1 d-flex align-items-center gap-1"><i class="bi bi-question-circle-fill text-secondary"></i> Original parent${escapeHtml(parentLabel)} is unavailable. Restoration requires selecting how to restore.</div>`;
                }
            }

            // Options container for subscenes needing parent resolution
            let parentChoiceControls = '';
            if (isSub && requiresParentChoice) {
                const parentOptionsHtml = activeMainScenes.map(p => {
                    const optText = `${p.number}: ${p.heading}`;
                    return `<option value="${escapeHtml(p.id)}">${escapeHtml(optText)}</option>`;
                }).join('');

                parentChoiceControls = `
                    <div class="mt-2 p-2 bg-white rounded border small" id="restoreOptions_${escapeHtml(sc.id)}">
                        <div class="fw-semibold text-dark mb-1">Choose Restoration Target:</div>
                        <div class="form-check mb-1">
                            <input class="form-check-input restore-choice-radio" type="radio" name="restoreChoice_${escapeHtml(sc.id)}" id="restoreAsMain_${escapeHtml(sc.id)}" value="main_scene" checked>
                            <label class="form-check-label text-dark" for="restoreAsMain_${escapeHtml(sc.id)}">
                                <strong>Restore as Main Scene</strong> (promotes sub-scene to an independent scene)
                            </label>
                        </div>
                        <div class="form-check">
                            <input class="form-check-input restore-choice-radio" type="radio" name="restoreChoice_${escapeHtml(sc.id)}" id="restoreAsParent_${escapeHtml(sc.id)}" value="specified_parent" ${activeMainScenes.length === 0 ? 'disabled' : ''}>
                            <label class="form-check-label text-dark" for="restoreAsParent_${escapeHtml(sc.id)}">
                                <strong>Choose an active parent scene:</strong>
                            </label>
                        </div>
                        <div class="mt-2 ms-2 ms-md-4" id="parentSelectWrapper_${escapeHtml(sc.id)}" style="display: none;">
                            ${activeMainScenes.length > 0 ? `
                                <select class="form-select form-select-sm" id="parentSelect_${escapeHtml(sc.id)}">
                                    ${parentOptionsHtml}
                                </select>
                            ` : `
                                <span class="text-danger small">No active main scenes available to attach to.</span>
                            `}
                        </div>
                    </div>
                `;
            }

            // Deleted timestamp
            let deletedAtText = '';
            if (sc.deleted_at) {
                try {
                    const dt = new Date(sc.deleted_at);
                    deletedAtText = `<span class="small text-muted" title="${escapeHtml(sc.deleted_at)}"><i class="bi bi-clock-history me-1"></i>Moved to Trash ${escapeHtml(dt.toLocaleDateString())} ${escapeHtml(dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))}</span>`;
                } catch (_) {}
            }

            const rawHeading = sc.heading || 'UNTITLED SCENE';

            return `
                <div class="card border rounded-3 p-3 bg-light shadow-sm scene-trash-item" id="trashedSceneCard_${escapeHtml(sc.id)}">
                    <!-- Desktop / Tablet Presentation (>= 768px) - Exact HEAD Layout -->
                    <div class="d-none d-md-flex align-items-start justify-content-between gap-3">
                        <div class="flex-grow-1 min-w-0">
                            <div class="d-flex align-items-center flex-wrap gap-2 mb-1">
                                ${sceneBadge}
                                ${typeBadges}
                                <span class="font-screenplay fw-bold text-dark text-truncate fs-6" title="${escapeHtml(rawHeading)}">${escapeHtml(rawHeading)}</span>
                            </div>
                            ${parentInfoHtml}
                            ${parentChoiceControls}
                            <div class="mt-2">
                                ${deletedAtText}
                            </div>
                        </div>

                        <!-- Action Button -->
                        <div class="flex-shrink-0 d-flex flex-column align-items-end gap-1">
                            <button type="button" class="btn btn-sm btn-success px-3 d-inline-flex align-items-center gap-1 btn-restore-scene"
                                id="btnRestoreScene_${escapeHtml(sc.id)}"
                                data-scene-id="${escapeHtml(sc.id)}"
                                data-is-sub="${isSub}"
                                data-requires-parent="${requiresParentChoice}">
                                <i class="bi bi-arrow-counterclockwise"></i>
                                <span>Restore</span>
                            </button>
                            <span class="small text-muted" style="font-size: 0.72rem;">Safe Recovery</span>
                        </div>
                    </div>

                    <!-- Mobile Presentation (< 768px) - Approved Mobile Stacked Layout -->
                    <div class="d-md-none d-flex flex-column align-items-stretch justify-content-between gap-3">
                        <div class="flex-grow-1 min-w-0 w-100">
                            <div class="d-flex align-items-center flex-wrap gap-2 mb-1">
                                ${sceneBadge}
                                ${typeBadges}
                                <span class="font-screenplay fw-bold text-dark text-break fs-6" title="${escapeHtml(rawHeading)}">${escapeHtml(rawHeading)}</span>
                            </div>
                            ${parentInfoHtml}
                            ${parentChoiceControls}
                            <div class="mt-2 text-break">
                                ${deletedAtText}
                            </div>
                        </div>

                        <!-- Action Button -->
                        <div class="flex-shrink-0 d-flex flex-column align-items-stretch gap-1 w-100 mt-2">
                            <button type="button" class="btn btn-sm btn-success px-3 d-inline-flex align-items-center justify-content-center gap-1 btn-restore-scene w-100"
                                data-scene-id="${escapeHtml(sc.id)}"
                                data-is-sub="${isSub}"
                                data-requires-parent="${requiresParentChoice}">
                                <i class="bi bi-arrow-counterclockwise"></i>
                                <span>Restore</span>
                            </button>
                            <span class="small text-muted text-center" style="font-size: 0.72rem;">Safe Recovery</span>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        listEl.innerHTML = itemsHtml;

        // Bind Radio Toggle for Parent Select Dropdowns
        trashedScenes.forEach(sc => {
            const isSub = Boolean(sc.is_sub_scene);
            const requiresParentChoice = isSub && (sc.parent_status === 'trashed' || sc.parent_status === 'missing');
            if (requiresParentChoice) {
                const radioMain = document.getElementById(`restoreAsMain_${sc.id}`);
                const radioParent = document.getElementById(`restoreAsParent_${sc.id}`);
                const selectWrapper = document.getElementById(`parentSelectWrapper_${sc.id}`);

                if (radioMain && radioParent && selectWrapper) {
                    radioMain.addEventListener('change', () => {
                        if (radioMain.checked) selectWrapper.style.display = 'none';
                    });
                    radioParent.addEventListener('change', () => {
                        if (radioParent.checked) selectWrapper.style.display = 'block';
                    });
                }
            }
        });

        // Bind Restore Button Clicks
        listEl.querySelectorAll('.btn-restore-scene').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                const sceneId = btn.dataset.sceneId;
                const requiresParent = btn.dataset.requiresParent === 'true';

                let payload = {};
                if (requiresParent) {
                    const radioParent = document.getElementById(`restoreAsParent_${sceneId}`);
                    if (radioParent && radioParent.checked) {
                        const selectEl = document.getElementById(`parentSelect_${sceneId}`);
                        const chosenParentId = selectEl ? selectEl.value : null;
                        if (!chosenParentId) {
                            alert('Please select an active parent scene.');
                            return;
                        }
                        payload = {
                            restore_as: 'specified_parent',
                            target_parent_id: parseInt(chosenParentId, 10)
                        };
                    } else {
                        payload = {
                            restore_as: 'main_scene'
                        };
                    }
                } else {
                    payload = {
                        restore_as: 'auto'
                    };
                }

                await this.restoreScene(sceneId, payload, btn);
            });
        });
    }

    async restoreScene(sceneId, payload, btnEl) {
        if (this.isRestoringScene) return;
        this.isRestoringScene = true;

        const originalBtnHtml = btnEl ? btnEl.innerHTML : 'Restore';
        if (btnEl) {
            btnEl.disabled = true;
            btnEl.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Restoring...';
        }

        const alertArea = document.getElementById('sceneTrashAlertArea');
        if (alertArea) {
            alertArea.style.display = 'none';
            alertArea.innerHTML = '';
        }

        try {
            const res = await fetch(`/scripts/api/${this.scriptId}/scenes/${sceneId}/restore/`, {
                method: 'POST',
                headers: this.getHeaders(),
                body: JSON.stringify(payload)
            });

            const data = await res.json().catch(() => null);

            if (!res.ok || !data || data.status !== 'ok') {
                let errMsg = 'Failed to restore scene';
                if (data && data.message) {
                    errMsg = data.message;
                } else if (res.status === 400) {
                    errMsg = 'Cannot restore scene: invalid restoration parameters.';
                } else if (res.status === 403) {
                    errMsg = 'Permission denied: you do not have permission to restore this scene.';
                } else if (res.status === 404) {
                    errMsg = 'Scene or screenplay not found.';
                } else if (res.status === 405) {
                    errMsg = 'Incorrect HTTP method.';
                } else if (res.status >= 500) {
                    errMsg = 'Server error occurred while restoring the scene. Please try again.';
                }
                throw new Error(errMsg);
            }

            // Successful restore!
            // 1. Remove the scene card from the trash list
            const cardEl = document.getElementById(`trashedSceneCard_${sceneId}`);
            if (cardEl) {
                cardEl.remove();
            }

            // 2. Refresh active Scene Navigator and stats
            if (data.scenes_tree) {
                this.renderScenesTree(data.scenes_tree);
            }
            if (data.script_stats) {
                this.updateStats(data.script_stats);
            }

            // 3. Refresh trash count badge
            await this.fetchSceneTrashCount();

            // 4. Check if trash list is now empty
            const remainingCards = document.querySelectorAll('.scene-trash-item');
            const emptyEl = document.getElementById('sceneTrashEmptyState');
            const statsEl = document.getElementById('sceneTrashFooterStats');
            if (remainingCards.length === 0) {
                if (emptyEl) emptyEl.style.display = 'block';
                if (statsEl) statsEl.innerText = '0 scenes in Trash';
            } else if (statsEl) {
                statsEl.innerText = `${remainingCards.length} trashed scene${remainingCards.length === 1 ? '' : 's'}`;
            }

            // 5. Show intercut fallback notice or success alert
            if (alertArea) {
                alertArea.innerHTML = '';
                if (data.intercut_fallback) {
                    const alertDiv = document.createElement('div');
                    alertDiv.className = 'alert alert-warning alert-dismissible fade show py-2 px-3 small d-flex align-items-center gap-2 mb-3';
                    alertDiv.setAttribute('role', 'alert');

                    const icon = document.createElement('i');
                    icon.className = 'bi bi-exclamation-triangle-fill text-warning flex-shrink-0 fs-6';
                    alertDiv.appendChild(icon);

                    const contentDiv = document.createElement('div');
                    const strong = document.createElement('strong');
                    strong.textContent = 'Intercut Notice: ';
                    contentDiv.appendChild(strong);
                    contentDiv.appendChild(document.createTextNode('The scene was restored, but its original intercut source is no longer available. It was restored as a normal scene.'));
                    alertDiv.appendChild(contentDiv);

                    const closeBtn = document.createElement('button');
                    closeBtn.type = 'button';
                    closeBtn.className = 'btn-close';
                    closeBtn.setAttribute('data-bs-dismiss', 'alert');
                    closeBtn.setAttribute('aria-label', 'Close');
                    alertDiv.appendChild(closeBtn);

                    alertArea.appendChild(alertDiv);
                    alertArea.style.display = 'block';
                } else {
                    const alertDiv = document.createElement('div');
                    alertDiv.className = 'alert alert-success alert-dismissible fade show py-2 px-3 small d-flex align-items-center gap-2 mb-3';
                    alertDiv.setAttribute('role', 'alert');

                    const icon = document.createElement('i');
                    icon.className = 'bi bi-check-circle-fill text-success flex-shrink-0 fs-6';
                    alertDiv.appendChild(icon);

                    const contentDiv = document.createElement('div');
                    contentDiv.textContent = data.message || 'Scene restored successfully!';
                    alertDiv.appendChild(contentDiv);

                    const closeBtn = document.createElement('button');
                    closeBtn.type = 'button';
                    closeBtn.className = 'btn-close';
                    closeBtn.setAttribute('data-bs-dismiss', 'alert');
                    closeBtn.setAttribute('aria-label', 'Close');
                    alertDiv.appendChild(closeBtn);

                    alertArea.appendChild(alertDiv);
                    alertArea.style.display = 'block';
                }
            }

            // If in edit mode and restoring might have added a scene, make sure read mode syncs if needed
            if (this.editorMode === 'read' && data.restored_scene_id) {
                // If the user desires to scroll to the restored scene:
                const restoredEl = document.getElementById(`read-scene-${data.restored_scene_id}`);
                if (restoredEl) {
                    restoredEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }
        } catch (err) {
            console.error('Scene restore error:', err);
            if (alertArea) {
                alertArea.innerHTML = '';
                const alertDiv = document.createElement('div');
                alertDiv.className = 'alert alert-danger alert-dismissible fade show py-2 px-3 small d-flex align-items-center gap-2 mb-3';
                alertDiv.setAttribute('role', 'alert');

                const icon = document.createElement('i');
                icon.className = 'bi bi-exclamation-octagon-fill text-danger flex-shrink-0 fs-6';
                alertDiv.appendChild(icon);

                const contentDiv = document.createElement('div');
                contentDiv.textContent = err.message || 'An error occurred while restoring the scene.';
                alertDiv.appendChild(contentDiv);

                const closeBtn = document.createElement('button');
                closeBtn.type = 'button';
                closeBtn.className = 'btn-close';
                closeBtn.setAttribute('data-bs-dismiss', 'alert');
                closeBtn.setAttribute('aria-label', 'Close');
                alertDiv.appendChild(closeBtn);

                alertArea.appendChild(alertDiv);
                alertArea.style.display = 'block';
            }
            if (btnEl) {
                btnEl.disabled = false;
                btnEl.innerHTML = originalBtnHtml;
            }
        } finally {
            this.isRestoringScene = false;
        }
    }

    // ----------------------------------------------------
    // PREVIOUS SCENE SELECTION (SUB-SCENE 2 & INTERCUT)
    // ----------------------------------------------------
    getPreviousScenes(includeSubScenes = false) {
        const flat = [];
        const traverse = (items) => {
            if (!items || !Array.isArray(items)) return;
            items.forEach(item => {
                flat.push(item);
                if (item.sub_scenes && item.sub_scenes.length > 0) {
                    traverse(item.sub_scenes);
                }
            });
        };
        traverse(this.scenesTree);

        const curIdx = flat.findIndex(s => Number(s.id) === Number(this.currentSceneId));
        if (curIdx <= 0) {
            return [];
        }

        const previousItems = flat.slice(0, curIdx);
        const seen = new Set();
        const eligible = [];
        for (const sc of previousItems) {
            if (includeSubScenes) {
                if (!seen.has(Number(sc.id))) {
                    seen.add(Number(sc.id));
                    eligible.push(sc);
                }
            } else {
                // Find parent if it is a sub-scene or use main scene
                const target = sc.is_sub_scene && sc.parent_scene_id
                    ? (previousItems.find(p => Number(p.id) === Number(sc.parent_scene_id)) || sc)
                    : sc;
                if (target && !seen.has(Number(target.id))) {
                    seen.add(Number(target.id));
                    eligible.push(target);
                }
            }
        }
        return eligible;
    }

    openSceneSelectModal(mode = 'subscene_2') {
        this.sceneSelectMode = mode;
        const titleEl = document.getElementById('editorSceneSelectModalTitle');
        const subtitleEl = document.getElementById('editorSceneSelectModalSubtitle');
        const searchEl = document.getElementById('editorSceneSelectSearch');

        if (titleEl) {
            titleEl.innerHTML = mode === 'subscene_2'
                ? '<i class="bi bi-diagram-2 me-2 text-primary"></i>Insert Sub-Scene From'
                : '<i class="bi bi-arrow-left-right me-2 text-primary"></i>Cut Back To';
        }
        if (subtitleEl) {
            subtitleEl.innerText = mode === 'subscene_2'
                ? 'Choose a previously written scene to create a sub-scene at current position'
                : 'Choose a previously written scene to cut back to at current position';
        }
        if (searchEl) {
            searchEl.value = '';
        }

        const includeSubScenes = (mode === 'intercut');
        const scenes = this.getPreviousScenes(includeSubScenes);
        this.renderSceneSelectItems(scenes);

        if (this.bsOffcanvas && this.offcanvasEl && this.offcanvasEl.classList.contains('show')) {
            this.bsOffcanvas.hide();
        }

        if (this.sceneSelectModalEl) {
            const modal = bootstrap.Modal.getOrCreateInstance(this.sceneSelectModalEl);
            modal.show();
            setTimeout(() => {
                if (searchEl) searchEl.focus();
            }, 300);
        }
    }

    renderSceneSelectItems(scenes, filterText = '') {
        const listEl = document.getElementById('editorSceneSelectList');
        const countEl = document.getElementById('editorSceneSelectCount');
        if (!listEl) return;

        const q = (filterText || '').toLowerCase().trim();
        const filtered = q
            ? scenes.filter(s => {
                const text = (s.full_display_heading || `${s.scene_identifier || s.display_number_formatted} : ${s.clean_heading || s.heading}`).toLowerCase();
                return text.includes(q);
            })
            : scenes;

        if (countEl) {
            countEl.innerText = `${filtered.length} scene${filtered.length === 1 ? '' : 's'} available`;
        }

        if (filtered.length === 0) {
            listEl.innerHTML = `
                <div class="p-4 text-center text-muted">
                    <i class="bi bi-info-circle me-1"></i> No previous scenes available
                </div>
            `;
            return;
        }

        const html = filtered.map(sc => {
            const isSubScene = Boolean(sc.is_sub_scene);
            const fullHeading = sc.full_display_heading || `${sc.scene_identifier || sc.display_number_formatted} : ${sc.clean_heading || sc.heading}`;
            const isCurrentTarget = this.currentSceneIntercutSourceId && Number(this.currentSceneIntercutSourceId) === Number(sc.id);
            const indentStyle = isSubScene ? 'padding-left: 1.75rem !important;' : '';
            const subSceneBadge = isSubScene ? '<span class="badge bg-secondary-subtle text-secondary me-2 px-1.5 py-0.5" style="font-size:0.65rem;">SUB-SCENE</span>' : '';
            const subScenePrefix = isSubScene ? '<span class="text-muted me-1">↳</span>' : '';
            const activeClass = isCurrentTarget ? 'border-primary bg-light' : '';

            return `
                <button type="button" class="list-group-item list-group-item-action d-flex align-items-center justify-content-between py-2 px-3 border-0 border-bottom editor-scene-select-item ${activeClass}" style="${indentStyle}" data-scene-id="${sc.id}">
                    <div class="d-flex align-items-center flex-wrap me-2 text-start">
                        ${subScenePrefix}
                        ${subSceneBadge}
                        <span class="font-screenplay font-malayalam fw-semibold text-dark text-wrap" style="word-break: break-word;">${fullHeading}</span>
                    </div>
                    <i class="bi bi-chevron-right text-muted ms-auto small flex-shrink-0"></i>
                </button>
            `;
        }).join('');

        listEl.innerHTML = html;

        listEl.querySelectorAll('.editor-scene-select-item').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                const sceneId = btn.dataset.sceneId;
                if (!sceneId || this.isCreatingScene) return;
                await this.submitSceneSelection(sceneId);
            });
        });
    }

    bindSceneSelectEvents() {
        const searchEl = document.getElementById('editorSceneSelectSearch');
        if (searchEl) {
            searchEl.addEventListener('input', (e) => {
                const includeSubScenes = (this.sceneSelectMode === 'intercut');
                const scenes = this.getPreviousScenes(includeSubScenes);
                this.renderSceneSelectItems(scenes, e.target.value);
            });
        }
    }

    async submitSceneSelection(sourceSceneId) {
        if (this.isCreatingScene) return;
        this.isCreatingScene = true;

        try {
            await this.flushSave();
        } catch (err) {
            console.error('Save failed before creating scene selection:', err);
            this.isCreatingScene = false;
            alert('Could not save the current scene. Scene creation was cancelled to protect your unsaved writing. Please retry once saved.');
            return;
        }

        const mode = this.sceneSelectMode;
        const endpoint = mode === 'subscene_2'
            ? `/scripts/api/${this.scriptId}/scenes/subscene-2/`
            : `/scripts/api/${this.scriptId}/scenes/intercut/`;

        try {
            this.setSaveStatus('saving', mode === 'subscene_2' ? 'Creating Sub-Scene From...' : 'Creating Cut Back Scene...');
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: this.getHeaders(),
                body: JSON.stringify({
                    source_scene_id: parseInt(sourceSceneId, 10),
                    current_scene_id: parseInt(this.currentSceneId, 10)
                })
            });

            const data = await res.json();
            if (!res.ok || data.status !== 'ok') {
                throw new Error(data.message || 'Failed to create scene');
            }

            if (this.sceneSelectModalEl) {
                const modal = bootstrap.Modal.getInstance(this.sceneSelectModalEl);
                if (modal) modal.hide();
            }

            this.renderScenesTree(data.scenes_tree);
            await this.switchScene(data.scene.id);
        } catch (err) {
            alert('Error: ' + err.message);
            this.setSaveStatus('error', 'Error creating scene');
        } finally {
            this.isCreatingScene = false;
        }
    }

    bindSceneSearch() {
        const desktopSearch = document.getElementById('sceneSearchInput');
        if (desktopSearch) {
            desktopSearch.addEventListener('input', (e) => {
                this.filterSceneItems(this.scenesList, e.target.value);
            });
        }
        const offcanvasSearch = document.getElementById('offcanvasSceneSearchInput');
        if (offcanvasSearch) {
            offcanvasSearch.addEventListener('input', (e) => {
                this.filterSceneItems(this.offcanvasScenesList, e.target.value);
            });
        }
    }

    filterSceneItems(container, term) {
        if (!container) return;
        const q = term.toLowerCase().trim();
        container.querySelectorAll('.scene-item').forEach(item => {
            const text = item.innerText.toLowerCase();
            item.style.display = text.includes(q) ? 'flex' : 'none';
        });
    }

    // ----------------------------------------------------
    // STATS & METRICS
    // ----------------------------------------------------
    calculateLiveStats() {
        let words = 0;
        let chars = 0;
        const blocks = this.pageContainer.querySelectorAll('.element-content');
        blocks.forEach(b => {
            const t = b.innerText.trim();
            if (t) {
                words += t.split(/\s+/).length;
                chars += t.length;
            }
        });

        if (this.wordCountEl) this.wordCountEl.innerText = words;
        if (this.charCountEl) this.charCountEl.innerText = chars;
        if (this.pageCountEl) {
            const estPages = words === 0 ? 1 : Math.max(1, Math.ceil(words / 220));
            this.pageCountEl.innerText = `~${estPages} pgs`;
        }
    }

    updateStats(stats) {
        if (!stats) return;
        if (this.wordCountEl) this.wordCountEl.innerText = stats.word_count;
        if (this.charCountEl) this.charCountEl.innerText = stats.char_count;
        if (this.pageCountEl) this.pageCountEl.innerText = `~${stats.estimated_pages} pgs`;
        if (this.sceneCountEl) {
            const primary = stats.primary_scene_count !== undefined ? stats.primary_scene_count : stats.scene_count;
            const sub = stats.sub_scene_count !== undefined ? stats.sub_scene_count : 0;
            this.sceneCountEl.innerText = sub > 0 ? `${primary} (${sub} sub)` : `${primary}`;
        }
        if (stats.primary_scene_count !== undefined) {
            this.updateNavHeadingCounts(stats.primary_scene_count, stats.sub_scene_count || 0);
        } else if (this.sidebarSceneCountEl) {
            this.sidebarSceneCountEl.innerText = stats.scene_count;
            if (this.offcanvasSceneCountEl) this.offcanvasSceneCountEl.innerText = stats.scene_count;
        }
    }

    // ----------------------------------------------------
    // TOOLBAR & SHORTCUTS
    // ----------------------------------------------------
    handleElementButtonClick(targetType) {
        let targetBlock = this.activeElementBlock;

        // If activeElementBlock is missing or detached from DOM, find focused or last block
        if (!targetBlock || !targetBlock.parentNode || targetBlock.parentNode !== this.pageContainer) {
            targetBlock = this.pageContainer.querySelector('.script-element-block.focused') ||
                          this.pageContainer.lastElementChild;
        }

        if (!targetBlock) {
            const newBlock = this.createElementBlock(targetType, '');
            const editable = newBlock.querySelector('.element-content');
            if (editable) {
                editable.focus();
                this.setCursorToStart(editable);
            }
            this.activeElementBlock = newBlock;
            this.updateActiveToolbarButton(targetType);
            if (this.currentTypeEl) {
                this.currentTypeEl.innerText = this.formatTypeLabel(targetType);
            }
            this.markDirty();
            this.calculateLiveStats();
            return;
        }

        const currentType = targetBlock.dataset.type;
        const editable = targetBlock.querySelector('.element-content');
        const currentText = editable ? editable.innerText.trim() : '';

        // If the current element has text OR is a scene_heading:
        // Always preserve previous content 100% and create the new element block immediately after.
        if (currentText !== '' || currentType === 'scene_heading') {
            const newBlock = this.createElementBlock(targetType, '', targetBlock);
            const newEditable = newBlock.querySelector('.element-content');
            if (newEditable) {
                newEditable.focus();
                this.setCursorToStart(newEditable);
            }
            document.querySelectorAll('.script-element-block.focused').forEach(b => b.classList.remove('focused'));
            newBlock.classList.add('focused');
            this.activeElementBlock = newBlock;
            this.updateActiveToolbarButton(targetType);
            if (this.currentTypeEl) {
                this.currentTypeEl.innerText = this.formatTypeLabel(targetType);
            }
            this.markDirty();
            this.calculateLiveStats();
        } else {
            // If the current element is completely empty (e.g. blank action/dialogue line):
            // Safely set its element type to targetType without altering any text.
            this.setElementType(targetBlock, targetType);
            const curEditable = targetBlock.querySelector('.element-content');
            if (curEditable) {
                curEditable.focus();
                this.setCursorToStart(curEditable);
            }
            document.querySelectorAll('.script-element-block.focused').forEach(b => b.classList.remove('focused'));
            targetBlock.classList.add('focused');
            this.activeElementBlock = targetBlock;
            this.updateActiveToolbarButton(targetType);
            if (this.currentTypeEl) {
                this.currentTypeEl.innerText = this.formatTypeLabel(targetType);
            }
            this.markDirty();
            this.calculateLiveStats();
        }
    }

    bindToolbarButtons() {
        document.querySelectorAll('.btn-element').forEach(btn => {
            btn.addEventListener('mousedown', (e) => {
                e.preventDefault();
            });

            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const targetType = btn.dataset.type;
                this.handleElementButtonClick(targetType);
            });
        });

        const btnTopAddScene = document.getElementById('btnTopAddScene');
        if (btnTopAddScene) {
            btnTopAddScene.addEventListener('click', async () => {
                await this.appendScene();
            });
        }

        const btnTopAddSubScene = document.getElementById('btnTopAddSubScene');
        if (btnTopAddSubScene) {
            btnTopAddSubScene.addEventListener('click', async () => {
                await this.addSubSceneDirect();
            });
        }

        const btnTopAddSubScene2 = document.getElementById('btnTopAddSubScene2');
        if (btnTopAddSubScene2) {
            btnTopAddSubScene2.addEventListener('click', () => {
                this.openSceneSelectModal('subscene_2');
            });
        }

        const btnTopAddIntercut = document.getElementById('btnTopAddIntercut');
        if (btnTopAddIntercut) {
            btnTopAddIntercut.addEventListener('click', () => {
                this.openSceneSelectModal('intercut');
            });
        }

        const btnStartSongSequence = document.getElementById('btnStartSongSequence');
        if (btnStartSongSequence) {
            btnStartSongSequence.addEventListener('click', (e) => {
                e.preventDefault();
                this.startSequence('song');
            });
        }

        const btnStartMontageSequence = document.getElementById('btnStartMontageSequence');
        if (btnStartMontageSequence) {
            btnStartMontageSequence.addEventListener('click', (e) => {
                e.preventDefault();
                this.startSequence('montage');
            });
        }

        const btnNextSequenceShot = document.getElementById('btnNextSequenceShot');
        if (btnNextSequenceShot) {
            btnNextSequenceShot.addEventListener('click', (e) => {
                e.preventDefault();
                this.createNextSequenceShot();
            });
        }

        const btnEndSequence = document.getElementById('btnEndSequence');
        if (btnEndSequence) {
            btnEndSequence.addEventListener('click', (e) => {
                e.preventDefault();
                this.endCurrentSequence();
            });
        }

        const btnSequenceDropdown = document.getElementById('btnSequenceDropdown');
        if (btnSequenceDropdown) {
            if (window.bootstrap && window.bootstrap.Dropdown) {
                window.bootstrap.Dropdown.getOrCreateInstance(btnSequenceDropdown, {
                    popperConfig: { strategy: 'fixed' }
                });
            }
            btnSequenceDropdown.addEventListener('show.bs.dropdown', () => {
                this.updateSequenceToolbarState();
            });
        }

        const btnToolbarUndo = document.getElementById('btnToolbarUndo');
        if (btnToolbarUndo) {
            btnToolbarUndo.addEventListener('click', (e) => {
                e.preventDefault();
                this.undo();
            });
        }

        const btnToolbarRedo = document.getElementById('btnToolbarRedo');
        if (btnToolbarRedo) {
            btnToolbarRedo.addEventListener('click', (e) => {
                e.preventDefault();
                this.redo();
            });
        }

        const btnToolbarCopy = document.getElementById('btnToolbarCopyCurrentScene');
        if (btnToolbarCopy) {
            btnToolbarCopy.addEventListener('click', async (e) => {
                e.preventDefault();
                await this.copyFullScene(this.currentSceneId);
            });
        }

        const btnSave = document.getElementById('btnSaveManual');
        if (btnSave) {
            btnSave.addEventListener('click', async () => {
                try {
                    await this.saveCurrentScene(true);
                } catch (err) {
                    console.error('Manual save failed:', err);
                }
            });
        }

        if (this.saveBadge) {
            this.saveBadge.addEventListener('click', () => {
                if (this.isDirty || this.saveBadge.classList.contains('error') || this.saveBadge.classList.contains('offline')) {
                    this.saveCurrentScene(true);
                }
            });
        }

        const btnFullscreen = document.getElementById('btnToggleFullscreen');
        if (btnFullscreen) {
            btnFullscreen.addEventListener('click', () => {
                const layout = document.querySelector('.editor-layout');
                layout.classList.toggle('fullscreen');
                btnFullscreen.innerHTML = layout.classList.contains('fullscreen')
                    ? '<i class="bi bi-fullscreen-exit me-2"></i>Exit Fullscreen'
                    : '<i class="bi bi-arrows-fullscreen me-2"></i>Fullscreen';
            });
        }
    }

    updateActiveToolbarButton(type) {
        document.querySelectorAll('.btn-element').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.type === type);
        });
    }

    bindGlobalEvents() {
        document.addEventListener('keydown', (e) => {
            const activeEl = document.activeElement;
            const isInsideModal = activeEl && (activeEl.closest('.modal.show') || document.querySelector('.modal.show'));
            const isSearchInput = activeEl && ( activeEl.id === 'sceneSearchInput' ||activeEl.id === 'offcanvasSceneSearchInput');
            const isFormInput = activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA') && !activeEl.classList.contains('heading-location-input');

            // 0. Undo & Redo Shortcuts
            if (!isInsideModal && !isSearchInput && !isFormInput) {
                const isCmdOrCtrl = e.ctrlKey || e.metaKey;
                const keyLower = (e.key || '').toLowerCase();
                const code = e.code || '';

                // Undo: Ctrl+Z / Cmd+Z (without Shift)
                if (isCmdOrCtrl && !e.altKey && !e.shiftKey && (keyLower === 'z' || code === 'KeyZ')) {
                    e.preventDefault();
                    this.undo();
                    return;
                }

                // Redo: Ctrl+Y / Cmd+Y / (Cmd/Ctrl + Shift + Z)
                const isRedoZ = isCmdOrCtrl && !e.altKey && e.shiftKey && (keyLower === 'z' || code === 'KeyZ');
                const isRedoY = isCmdOrCtrl && !e.altKey && !e.shiftKey && (keyLower === 'y' || code === 'KeyY');
                if (isRedoZ || isRedoY) {
                    e.preventDefault();
                    this.redo();
                    return;
                }
            }

            // 1. Save Scene: Ctrl + S / Cmd + S
            if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && (e.key === 's' || e.key === 'S' || e.code === 'KeyS')) {
                e.preventDefault();
                this.saveCurrentScene(true);
                return;
            }

            // 2. Find & Replace: Ctrl + F / Cmd + F
            if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && (e.key === 'f' || e.key === 'F' || e.code === 'KeyF')) {
                e.preventDefault();
                const findModal = new bootstrap.Modal(document.getElementById('findReplaceModal'));
                findModal.show();
                setTimeout(() => {
                    const input = document.getElementById('findInput');
                    if (input) input.focus();
                }, 300);
                return;
            }

            // 3. Screenplay Element Shortcuts: Ctrl + 1 to Ctrl + 7
            if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && !isInsideModal && !isSearchInput) {
                let digit = null;
                if (e.key >= '1' && e.key <= '7') {
                    digit = e.key;
                } else if (e.code && e.code.startsWith('Digit')) {
                    const d = e.code.slice(5);
                    if (d >= '1' && d <= '7') digit = d;
                } else if (e.code && e.code.startsWith('Numpad')) {
                    const d = e.code.slice(6);
                    if (d >= '1' && d <= '7') digit = d;
                }

                if (digit) {
                    const typeMap = {
                        '1': 'scene_heading',
                        '2': 'action',
                        '3': 'character',
                        '4': 'dialogue',
                        '5': 'parenthetical',
                        '6': 'transition',
                        '7': 'note'
                    };
                    const targetType = typeMap[digit];
                    if (targetType) {
                        e.preventDefault();
                        this.handleElementButtonClick(targetType);
                        return;
                    }
                }
            }

            // 4. Scene Management Shortcuts: Alt + S, Alt + U, Alt + R, Alt + B
            if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey && !isInsideModal && !isSearchInput) {
                const keyLower = (e.key || '').toLowerCase();
                const code = e.code || '';

                if (keyLower === 's' || code === 'KeyS') {
                    e.preventDefault();
                    this.appendScene();
                    return;
                }
                if (keyLower === 'u' || code === 'KeyU') {
                    e.preventDefault();
                    this.addSubSceneDirect();
                    return;
                }
                if (keyLower === 'r' || code === 'KeyR') {
                    e.preventDefault();
                    this.openSceneSelectModal('subscene_2');
                    return;
                }
                if (keyLower === 'b' || code === 'KeyB') {
                    e.preventDefault();
                    this.openSceneSelectModal('intercut');
                    return;
                }
            }
        });

        window.addEventListener('beforeunload', (e) => {
            if (this.isDirty || this.isSaving) {
                e.preventDefault();
                e.returnValue = 'You have unsaved changes in your screenplay!';
                return e.returnValue;
            }
        });

        document.addEventListener('click', (e) => {
            if (this.autocompleteDropdown && !this.autocompleteDropdown.contains(e.target) && !e.target.closest('.script-element-block[data-type="character"]')) {
                this.hideAutocomplete();
            }
            if (!e.target.closest('#elementSuggestionPopup')) {
                this.hideSuggestionPopup();
            }
        });
    }

    bindNetworkEvents() {
        window.addEventListener('online', () => {
            console.log('Network connection restored.');
            if (this.isDirty) {
                this.saveCurrentScene(true);
            } else {
                this.setSaveStatus('saved', 'Saved ✓');
            }
        });

        window.addEventListener('offline', () => {
            console.warn('Network connection lost.');
            this.setSaveStatus('offline', 'Offline / connection problem');
        });
    }

    bindSwipeNavigation() {
        if (!this.offcanvasEl) return;

        const editorMain = document.querySelector('.editor-main') || this.editorLayout;
        const offcanvasEl = this.offcanvasEl;

        const getOffcanvasInstance = () => {
            return (typeof bootstrap !== 'undefined' && bootstrap.Offcanvas)
                ? bootstrap.Offcanvas.getOrCreateInstance(offcanvasEl)
                : this.bsOffcanvas;
        };

        // --- 1. Swipe LEFT on Editor area -> Open Scene Order ---
        if (editorMain) {
            let editorStartX = 0;
            let editorStartY = 0;
            let editorStartTime = 0;
            let isEditorEligible = false;

            editorMain.addEventListener('touchstart', (e) => {
                if (e.touches.length !== 1) {
                    isEditorEligible = false;
                    return;
                }

                // If drawer is already open, do not handle opening
                if (offcanvasEl.classList.contains('show')) {
                    isEditorEligible = false;
                    return;
                }

                const target = e.target;
                const elem = target instanceof Element ? target : (target && target.parentElement);
                if (
                    !elem ||
                    elem.isContentEditable ||
                    (elem.closest && elem.closest('[contenteditable="true"], input, textarea, select, button, a, .modal, .modal-dialog, .dropdown, .dropdown-menu, .btn'))
                ) {
                    isEditorEligible = false;
                    return;
                }

                // Ignore if user has active text selection
                const selection = window.getSelection();
                if (selection && selection.toString().trim().length > 0) {
                    isEditorEligible = false;
                    return;
                }

                const touch = e.touches[0];
                const startX = touch.clientX;

                // Edge protection: ignore gestures beginning within 35px of screen edges
                if (startX <= 35 || startX >= (window.innerWidth - 35)) {
                    isEditorEligible = false;
                    return;
                }

                editorStartX = startX;
                editorStartY = touch.clientY;
                editorStartTime = Date.now();
                isEditorEligible = true;
            }, { passive: true });

            editorMain.addEventListener('touchend', (e) => {
                if (!isEditorEligible || !e.changedTouches || e.changedTouches.length !== 1) {
                    return;
                }

                const touch = e.changedTouches[0];
                const deltaX = touch.clientX - editorStartX;
                const deltaY = touch.clientY - editorStartY;
                const elapsedTime = Date.now() - editorStartTime;

                // Deliberate horizontal swipe within 550ms, dominant horizontal movement
                if (
                    elapsedTime <= 550 &&
                    Math.abs(deltaY) < 60 &&
                    deltaX <= -70 &&
                    Math.abs(deltaX) >= Math.abs(deltaY) * 1.7
                ) {
                    const inst = getOffcanvasInstance();
                    if (inst) {
                        inst.show();
                    }
                }
            }, { passive: true });
        }

        // --- 2. Swipe RIGHT on Scene Order panel -> Close Scene Order ---
        if (offcanvasEl) {
            let drawerStartX = 0;
            let drawerStartY = 0;
            let drawerStartTime = 0;
            let isDrawerEligible = false;

            offcanvasEl.addEventListener('touchstart', (e) => {
                if (e.touches.length !== 1) {
                    isDrawerEligible = false;
                    return;
                }

                // Only handle if drawer is currently open
                if (!offcanvasEl.classList.contains('show')) {
                    isDrawerEligible = false;
                    return;
                }

                const target = e.target;
                const elem = target instanceof Element ? target : (target && target.parentElement);
                if (
                    !elem ||
                    (elem.closest && elem.closest('input, textarea, select, button, a, .dropdown, .dropdown-menu, .modal, .modal-dialog, .btn'))
                ) {
                    isDrawerEligible = false;
                    return;
                }

                const touch = e.touches[0];
                const startX = touch.clientX;

                // Ignore extreme screen edge buffer
                if (startX <= 35 || startX >= (window.innerWidth - 35)) {
                    isDrawerEligible = false;
                    return;
                }

                drawerStartX = startX;
                drawerStartY = touch.clientY;
                drawerStartTime = Date.now();
                isDrawerEligible = true;
            }, { passive: true });

            offcanvasEl.addEventListener('touchend', (e) => {
                if (!isDrawerEligible || !e.changedTouches || e.changedTouches.length !== 1) {
                    return;
                }

                const touch = e.changedTouches[0];
                const deltaX = touch.clientX - drawerStartX;
                const deltaY = touch.clientY - drawerStartY;
                const elapsedTime = Date.now() - drawerStartTime;

                // Deliberate horizontal swipe RIGHT to close within 550ms
                if (
                    elapsedTime <= 550 &&
                    Math.abs(deltaY) < 60 &&
                    deltaX >= 70 &&
                    Math.abs(deltaX) >= Math.abs(deltaY) * 1.7
                ) {
                    const inst = getOffcanvasInstance();
                    if (inst) {
                        inst.hide();
                    }
                }
            }, { passive: true });
        }
    }

    // ----------------------------------------------------
    // FIND AND REPLACE
    // ----------------------------------------------------
    bindFindReplace() {
        const btnFindNext = document.getElementById('btnFindNext');
        const btnReplace = document.getElementById('btnReplace');
        const btnReplaceAll = document.getElementById('btnReplaceAll');

        if (btnFindNext) btnFindNext.addEventListener('click', () => this.findNext());
        if (btnReplace) btnReplace.addEventListener('click', () => this.replaceCurrent());
        if (btnReplaceAll) btnReplaceAll.addEventListener('click', () => this.replaceAll());
    }

    findNext() {
        const term = document.getElementById('findInput').value;
        if (!term) return;

        const blocks = this.pageContainer.querySelectorAll('.element-content');
        for (let b of blocks) {
            const text = b.innerText;
            const idx = text.toLowerCase().indexOf(term.toLowerCase());
            if (idx !== -1) {
                b.focus();
                const range = document.createRange();
                const textNode = b.firstChild || b;
                if (textNode.nodeType === Node.TEXT_NODE) {
                    range.setStart(textNode, idx);
                    range.setEnd(textNode, idx + term.length);
                    const sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                    return;
                }
            }
        }
        alert(`No more matches found for "${term}"`);
    }

    replaceCurrent() {
        const findTerm = document.getElementById('findInput').value;
        const replaceTerm = document.getElementById('replaceInput').value;
        if (!findTerm) return;

        const sel = window.getSelection();
        if (sel && sel.toString().toLowerCase() === findTerm.toLowerCase()) {
            document.execCommand('insertText', false, replaceTerm);
            this.markDirty();
            this.findNext();
        } else {
            this.findNext();
        }
    }

    replaceAll() {
        const findTerm = document.getElementById('findInput').value;
        const replaceTerm = document.getElementById('replaceInput').value;
        if (!findTerm) return;

        let count = 0;
        const blocks = this.pageContainer.querySelectorAll('.element-content');
        blocks.forEach(b => {
            if (b.innerText.toLowerCase().includes(findTerm.toLowerCase())) {
                const regex = new RegExp(findTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
                b.innerText = b.innerText.replace(regex, replaceTerm);
                count++;
            }
        });

        if (count > 0) {
            this.markDirty();
            this.calculateLiveStats();
            alert(`Replaced ${count} occurrences.`);
        } else {
            alert(`No matches found for "${findTerm}"`);
        }
    }

    setCursorToEnd(el) {
        el.focus();
        if (typeof window.getSelection !== "undefined" && typeof document.createRange !== "undefined") {
            const range = document.createRange();
            range.selectNodeContents(el);
            range.collapse(false);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
        }
    }

    setCursorToStart(el) {
        el.focus();
        if (typeof window.getSelection !== "undefined" && typeof document.createRange !== "undefined") {
            const range = document.createRange();
            range.selectNodeContents(el);
            range.collapse(true);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
        }
    }

    // ----------------------------------------------------
    // READ MODE / EDIT MODE STATE ENGINE
    // ----------------------------------------------------
    setEditorMode(mode, scrollTarget = true) {
        this.editorMode = mode;
        const isEditMode = (mode === 'edit');
        if (this.editorRoot) {
            this.editorRoot.dataset.mode = mode;
        }
        document.body.classList.toggle('editor-edit-mode', isEditMode);
        document.body.classList.toggle('editor-read-mode', !isEditMode);

        const toolbars = document.getElementById('editorTopToolbarsPinned');
        if (toolbars) toolbars.style.display = (mode === 'read') ? 'none' : '';
        if (this.pageContainer) this.pageContainer.style.display = (mode === 'read') ? 'none' : '';
        if (this.readModeContainer) this.readModeContainer.style.display = (mode === 'read') ? 'block' : 'none';

        if (mode === 'read') {
            if (this.btnEditFab) this.btnEditFab.style.display = 'flex';
            if (this.btnDoneFab) this.btnDoneFab.style.display = 'none';
            this.hideSuggestionPopup();
            this.hideAutocomplete();

            // Prevent mobile keyboard from remaining open & blur contenteditable
            if (document.activeElement && typeof document.activeElement.blur === 'function') {
                document.activeElement.blur();
            }

            if (scrollTarget) {
                const targetId = this.readModeActiveSceneId || this.currentSceneId;
                if (targetId) {
                    const targetSceneEl = document.getElementById(`read-scene-${targetId}`);
                    if (targetSceneEl) {
                        targetSceneEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }
                }
            }
        } else {
            // Edit Mode
            if (this.btnEditFab) this.btnEditFab.style.display = 'none';
            if (this.btnDoneFab) this.btnDoneFab.style.display = 'flex';
            // Explicit user click/tap focuses elements without automatic focus or mobile keyboard popping
        }
    }

    bindModeToggleEvents() {
        if (this.btnEditFab) {
            this.btnEditFab.addEventListener('click', async (e) => {
                e.preventDefault();
                if (this._isEnteringEditMode) return;
                this._isEnteringEditMode = true;
                try {
                    // Determine which scene is currently closest in view within continuous Read Mode
                    const visibleSceneId = this.findVisibleReadModeSceneId();
                    const targetSceneId = Number(this.readModeActiveSceneId || visibleSceneId || this.currentSceneId);

                    const canvasLoadedId = this.pageContainer && this.pageContainer.dataset ? Number(this.pageContainer.dataset.loadedSceneId) : null;
                    if (targetSceneId && (Number(this.currentSceneId) !== targetSceneId || canvasLoadedId !== targetSceneId)) {
                        await this.switchScene(targetSceneId);
                    }

                    // Verify canvas represents intended scene
                    const verifiedLoadedId = this.pageContainer && this.pageContainer.dataset ? Number(this.pageContainer.dataset.loadedSceneId) : null;
                    if (!verifiedLoadedId || verifiedLoadedId !== targetSceneId || Number(this.currentSceneId) !== targetSceneId) {
                        console.error(`Cannot enter Edit Mode: Canvas represents scene ${verifiedLoadedId}, expected ${targetSceneId}`);
                        alert('Could not safely load the scene for editing. Please try again.');
                        return;
                    }

                    this.setEditorMode('edit');
                } catch (err) {
                    console.error('Error transitioning from Read Mode to Edit Mode:', err);
                    alert('An error occurred while opening the scene in Edit Mode. Please retry.');
                } finally {
                    this._isEnteringEditMode = false;
                }
            });
        }

        if (this.btnDoneFab) {
            this.btnDoneFab.addEventListener('click', async (e) => {
                e.preventDefault();
                await this.handleDoneClick();
            });
        }
    }

    findVisibleReadModeSceneId() {
        const scenes = document.querySelectorAll('.read-mode-scene');
        if (!scenes.length) return this.readModeActiveSceneId || this.currentSceneId;
        const container = document.getElementById('editorCanvasContainer');
        const containerTop = container ? container.getBoundingClientRect().top : 0;
        let closestId = null;
        let minDistance = Infinity;

        scenes.forEach(sec => {
            const rect = sec.getBoundingClientRect();
            const distance = Math.abs(rect.top - containerTop);
            if (distance < minDistance) {
                minDistance = distance;
                closestId = sec.dataset.sceneId;
            }
        });
        return closestId ? Number(closestId) : (this.readModeActiveSceneId || this.currentSceneId);
    }

    async handleDoneClick() {
        try {
            this.setSaveStatus('saving', 'Saving before exiting...');
            await this.flushSave();

            // Extract the saved payload to update Read Mode DOM immediately
            const payload = this.extractScenePayload();
            this.updateReadModeScene(this.currentSceneId, payload);

            this.readModeActiveSceneId = Number(this.currentSceneId);
            this.setEditorMode('read', true);
            this.setSaveStatus('saved', 'Saved ✓');
        } catch (err) {
            console.error('Save failed on Done:', err);
            this.setSaveStatus('error', 'Save failed. Changes kept in Edit Mode.');
            alert('Failed to save screenplay changes. You remain in Edit Mode so your changes are not lost.');
        }
    }

    setupReadModeScrollObserver() {
        if (!('IntersectionObserver' in window)) return;
        if (this.readModeObserver) {
            this.readModeObserver.disconnect();
        }

        const options = {
            root: null,
            rootMargin: '0px 0px -60% 0px',
            threshold: 0
        };

        this.readModeObserver = new IntersectionObserver((entries) => {
            if (this.editorMode !== 'read' || this.isNavigatingToScene) return;
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const sceneId = entry.target.dataset.sceneId;
                    if (sceneId) {
                        this.readModeActiveSceneId = Number(sceneId);
                        document.querySelectorAll('.scene-item').forEach(item => {
                            item.classList.toggle('active', Number(item.dataset.id) === Number(sceneId));
                        });
                    }
                }
            });
        }, options);

        const scenes = document.querySelectorAll('.read-mode-scene');
        scenes.forEach(sec => this.readModeObserver.observe(sec));
    }

    updateReadModeScene(sceneId, payload) {
        let sceneSection = document.getElementById(`read-scene-${sceneId}`);
        if (!sceneSection && this.readModeContainer) {
            sceneSection = document.createElement('section');
            sceneSection.className = 'read-mode-scene';
            sceneSection.id = `read-scene-${sceneId}`;
            sceneSection.dataset.sceneId = sceneId;

            const headingDiv = document.createElement('div');
            headingDiv.className = 'read-scene-heading font-screenplay';
            const idSpan = document.createElement('span');
            idSpan.className = 'read-scene-identifier';
            headingDiv.appendChild(idSpan);
            sceneSection.appendChild(headingDiv);

            const elementsDiv = document.createElement('div');
            elementsDiv.className = 'read-scene-elements';
            sceneSection.appendChild(elementsDiv);

            this.readModeContainer.appendChild(sceneSection);
            this.setupReadModeScrollObserver();
        }
        if (!sceneSection || !payload) return;

        // 1. Update Heading
        const headingEl = sceneSection.querySelector('.read-scene-identifier');
        if (headingEl) {
            const scMeta = (this.scenesTree || []).find(s => Number(s.id) === Number(sceneId));
            if (scMeta && scMeta.full_display_heading) {
                headingEl.innerText = scMeta.full_display_heading;
            } else {
                const currentIdent = (scMeta && (scMeta.nav_identifier || scMeta.scene_identifier || scMeta.display_number || (scMeta.scene_number ? 'Scene ' + scMeta.scene_number : '')))
                    || this.currentSceneIdentifier
                    || (this.currentSceneIsSub ? 'Sub-Scene' : 'Scene');
                const cleanHeading = (payload.heading || (scMeta && scMeta.heading) || '').replace(/^(?:Scene\s+\d+(?:\.[A-Za-z]+)?\s*[:—\-]\s*)+/i, '').trim();
                headingEl.innerText = cleanHeading ? `${currentIdent} : ${cleanHeading}` : `${currentIdent} : UNTITLED SCENE`;
            }
        }

        // 2. Update Elements
        const elementsContainer = sceneSection.querySelector('.read-scene-elements');
        if (elementsContainer && payload.elements) {
            elementsContainer.innerHTML = '';
            (payload.elements || []).forEach(elem => {
                if (elem.element_type !== 'scene_heading') {
                    const block = document.createElement('div');
                    block.className = `read-element-block element-type-${elem.element_type}`;
                    const contentStr = (elem.content || '').trim();
                    if (elem.element_type === 'shot') {
                        if (contentStr === 'SONG BEGINS' || contentStr === 'MONTAGE BEGINS') {
                            block.classList.add('sequence-marker', 'sequence-marker-start');
                        } else if (contentStr === 'SONG ENDS' || contentStr === 'MONTAGE ENDS') {
                            block.classList.add('sequence-marker', 'sequence-marker-end');
                        } else if (/^\d+\.\s*/.test(contentStr)) {
                            block.classList.add('sequence-shot-heading');
                        }
                    }
                    const contentDiv = document.createElement('div');
                    contentDiv.className = 'element-content font-screenplay font-malayalam';
                    contentDiv.innerText = elem.content || '';
                    block.appendChild(contentDiv);
                    elementsContainer.appendChild(block);
                }
            });
        }

        // 3. Update Transition if present (only if the scene does not already end with an explicit transition)
        let hasEndingTransition = false;
        if (payload.elements && Array.isArray(payload.elements)) {
            for (let i = payload.elements.length - 1; i >= 0; i--) {
                const elem = payload.elements[i];
                const content = (elem.content || '').trim();
                if (!content) continue;
                if (elem.element_type === 'note') continue;
                if (elem.element_type === 'transition') {
                    hasEndingTransition = true;
                } else if (elem.element_type === 'shot') {
                    const uc = content.toUpperCase();
                    if (uc === 'SONG ENDS' || uc === 'MONTAGE ENDS' || uc === 'SONG BEGINS' || uc === 'MONTAGE BEGINS') {
                        hasEndingTransition = true;
                    }
                }
                break;
            }
        } else if (elementsContainer) {
            const elementBlocks = Array.from(elementsContainer.querySelectorAll(':scope > .read-element-block'));
            for (let i = elementBlocks.length - 1; i >= 0; i--) {
                const block = elementBlocks[i];
                const content = (block.querySelector('.element-content')?.innerText || '').trim();
                if (!content) continue;
                if (block.classList.contains('element-type-note')) continue;
                if (block.classList.contains('element-type-transition')) {
                    hasEndingTransition = true;
                } else if (block.classList.contains('element-type-shot') || block.classList.contains('sequence-marker')) {
                    const uc = content.toUpperCase();
                    if (uc === 'SONG ENDS' || uc === 'MONTAGE ENDS' || uc === 'SONG BEGINS' || uc === 'MONTAGE BEGINS') {
                        hasEndingTransition = true;
                    }
                }
                break;
            }
        }

        let transEl = Array.from(sceneSection.children).find(child => child.classList && child.classList.contains('read-element-block') && child.classList.contains('element-type-transition'));
        let rawTransition;
        if (payload.transition !== undefined) {
            rawTransition = payload.transition;
        } else {
            rawTransition = this.currentSceneTransition !== undefined ? this.currentSceneTransition : 'CUT TO:';
        }
        const transitionText = (rawTransition === null || rawTransition === undefined) ? '' : String(rawTransition).trim();

        if (transitionText && !hasEndingTransition) {
            if (!transEl) {
                transEl = document.createElement('div');
                transEl.className = 'read-element-block element-type-transition';
                const transContent = document.createElement('div');
                transContent.className = 'element-content font-screenplay';
                transEl.appendChild(transContent);
                sceneSection.appendChild(transEl);
            }
            const transContent = transEl.querySelector('.element-content');
            if (transContent) {
                transContent.innerText = transitionText;
            }
        } else if (transEl) {
            transEl.remove();
        }
    }

    // ----------------------------------------------------
    // CONTEXTUAL ELEMENT SUGGESTION POPUP
    // ----------------------------------------------------
    bindSuggestionPopupEvents() {
        const updateIfVisible = () => {
            if (this.suggestionPopup && this.suggestionPopup.style.display !== 'none' && this.activeSuggestionBlock) {
                this.positionContextualPopup(this.activeSuggestionBlock);
            }
            if (this.autocompleteDropdown && this.autocompleteDropdown.style.display !== 'none' && this.activeAutocompleteEditable) {
                const rect = this.activeAutocompleteEditable.getBoundingClientRect();
                if (rect.bottom < 0 || rect.top > window.innerHeight) {
                    this.hideAutocomplete();
                } else {
                    this.positionAutocomplete(this.activeAutocompleteEditable);
                }
            }
        };

        window.addEventListener('resize', updateIfVisible, { passive: true });

        if (window.visualViewport) {
            window.visualViewport.addEventListener('resize', updateIfVisible, { passive: true });
            window.visualViewport.addEventListener('scroll', updateIfVisible, { passive: true });
        }

        const canvasContainer = document.getElementById('editorCanvasContainer');
        if (canvasContainer) {
            canvasContainer.addEventListener('scroll', updateIfVisible, { passive: true });
        }
        window.addEventListener('scroll', updateIfVisible, { passive: true });
    }

    getVisibleViewport() {
        if (window.visualViewport) {
            const vv = window.visualViewport;
            return {
                top: vv.offsetTop,
                bottom: vv.offsetTop + vv.height,
                height: vv.height,
                left: vv.offsetLeft,
                right: vv.offsetLeft + vv.width,
                width: vv.width
            };
        }
        return {
            top: 0,
            bottom: window.innerHeight,
            height: window.innerHeight,
            left: 0,
            right: window.innerWidth,
            width: window.innerWidth
        };
    }

    getCaretRect(targetBlock) {
        // 1. Try Selection Range rect
        const sel = window.getSelection();
        if (sel && sel.rangeCount > 0) {
            try {
                const range = sel.getRangeAt(0);
                if (targetBlock && targetBlock.contains(range.startContainer)) {
                    const rect = range.getBoundingClientRect();
                    if (rect && (rect.width > 0 || rect.height > 0 || rect.top !== 0 || rect.bottom !== 0)) {
                        return rect;
                    }
                    const rects = range.getClientRects();
                    if (rects && rects.length > 0) {
                        return rects[0];
                    }
                }
            } catch (e) {
                // Ignore range selection errors
            }
        }

        // 2. Active editable element rect
        if (targetBlock) {
            const ed = targetBlock.querySelector('.element-content:not(.d-none)') || targetBlock.querySelector('.element-content');
            if (ed) {
                const edRect = ed.getBoundingClientRect();
                if (edRect && (edRect.width > 0 || edRect.height > 0 || edRect.top !== 0 || edRect.bottom !== 0)) {
                    return edRect;
                }
            }
            // 3. Target block rect
            const bRect = targetBlock.getBoundingClientRect();
            if (bRect && (bRect.width > 0 || bRect.height > 0 || bRect.top !== 0 || bRect.bottom !== 0)) {
                return bRect;
            }
        }

        return null;
    }

    ensureBlockVisible(block) {
        if (!block) return false;
        const rect = block.getBoundingClientRect();
        const vv = this.getVisibleViewport();

        const toolbars = document.getElementById('editorTopToolbarsPinned');
        const toolbarsBottom = (toolbars && toolbars.style.display !== 'none')
            ? toolbars.getBoundingClientRect().bottom
            : 0;

        const statsBar = document.querySelector('.editor-stats-bar');
        const statsBarTop = statsBar ? statsBar.getBoundingClientRect().top : vv.bottom;

        const safeTop = Math.max(vv.top, toolbarsBottom) + 20;
        const safeBottom = Math.min(vv.bottom, statsBarTop) - 48;

        if (rect.top < safeTop || rect.bottom > safeBottom) {
            block.scrollIntoView({
                behavior: 'auto',
                block: 'center',
                inline: 'nearest'
            });
            return true;
        }
        return false;
    }

    positionContextualPopup(targetBlock = this.activeSuggestionBlock) {
        if (!this.suggestionPopup || !targetBlock || this.suggestionPopup.style.display === 'none') return;

        const caretRect = this.getCaretRect(targetBlock);
        if (!caretRect) return;

        const vv = this.getVisibleViewport();

        const toolbars = document.getElementById('editorTopToolbarsPinned');
        const toolbarsBottom = (toolbars && toolbars.style.display !== 'none')
            ? toolbars.getBoundingClientRect().bottom
            : 0;

        const statsBar = document.querySelector('.editor-stats-bar');
        const statsBarTop = statsBar ? statsBar.getBoundingClientRect().top : vv.bottom;

        const safeTop = Math.max(vv.top, toolbarsBottom) + 8;
        const safeBottom = Math.min(vv.bottom, statsBarTop) - 8;

        const popupRect = this.suggestionPopup.getBoundingClientRect();
        const popupHeight = popupRect.height || 34;
        const popupWidth = popupRect.width || 180;

        const GAP = 6;
        const spaceBelow = safeBottom - (caretRect.bottom + GAP);
        const spaceAbove = (caretRect.top - GAP) - safeTop;

        let topPos;
        // Prefer placing below caret if sufficient space exists, otherwise flip above
        if (spaceBelow >= popupHeight) {
            topPos = caretRect.bottom + GAP;
        } else if (spaceAbove >= popupHeight) {
            topPos = caretRect.top - popupHeight - GAP;
        } else if (spaceBelow >= spaceAbove) {
            topPos = caretRect.bottom + GAP;
        } else {
            topPos = caretRect.top - popupHeight - GAP;
        }

        // Hard bounds guarantee: popup must never extend into the virtual keyboard
        // or underneath the bottom stats bar, and must never go above pinned toolbars
        if (topPos + popupHeight > safeBottom) {
            topPos = safeBottom - popupHeight;
        }
        if (topPos < safeTop) {
            topPos = safeTop;
        }

        // Horizontal positioning: align near left of caret/block, clamped to visible viewport
        const MARGIN_X = 12;
        let leftPos = caretRect.left;
        const minLeft = (vv.left || 0) + MARGIN_X;
        const maxLeft = Math.max(minLeft, (vv.right || window.innerWidth) - popupWidth - MARGIN_X);
        leftPos = Math.max(minLeft, Math.min(leftPos, maxLeft));

        this.suggestionPopup.style.position = 'fixed';
        this.suggestionPopup.style.top = `${Math.round(topPos)}px`;
        this.suggestionPopup.style.left = `${Math.round(leftPos)}px`;
    }

    positionSuggestionPopup(targetBlock) {
        this.positionContextualPopup(targetBlock);
    }

    showSuggestionPopup(targetBlock, suggestions) {
        if (!this.suggestionPopup || !suggestions || !suggestions.length) return;
        this.activeSuggestionBlock = targetBlock;
        this.activeSuggestionIndex = -1;

        this.suggestionPopup.innerHTML = '';
        suggestions.forEach((sug) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'suggestion-chip';
            btn.dataset.suggestion = sug.type;
            btn.innerText = sug.label;
            btn.setAttribute('role', 'option');
            btn.addEventListener('mousedown', (e) => {
                e.preventDefault(); // prevent blur before action
            });
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                this.applySuggestion(sug.type, targetBlock);
            });
            this.suggestionPopup.appendChild(btn);
        });

        this.suggestionPopup.style.position = 'fixed';
        this.suggestionPopup.style.display = 'inline-flex';

        const didScroll = this.ensureBlockVisible(targetBlock);

        this.positionContextualPopup(targetBlock);

        requestAnimationFrame(() => {
            this.positionContextualPopup(targetBlock);
            requestAnimationFrame(() => {
                this.positionContextualPopup(targetBlock);
            });
        });

        if (didScroll) {
            setTimeout(() => {
                this.positionContextualPopup(targetBlock);
            }, 180);
        }
    }

    hideSuggestionPopup() {
        if (this.suggestionPopup) {
            this.suggestionPopup.style.display = 'none';
            this.suggestionPopup.innerHTML = '';
        }
        this.activeSuggestionBlock = null;
        this.activeSuggestionIndex = -1;
    }

    navigateSuggestions(delta) {
        if (!this.suggestionPopup) return;
        const chips = this.suggestionPopup.querySelectorAll('.suggestion-chip');
        if (!chips.length) return;

        chips.forEach(c => c.classList.remove('active'));
        this.activeSuggestionIndex += delta;
        if (this.activeSuggestionIndex >= chips.length) this.activeSuggestionIndex = 0;
        if (this.activeSuggestionIndex < 0) this.activeSuggestionIndex = chips.length - 1;

        chips[this.activeSuggestionIndex].classList.add('active');
    }

    applySuggestion(suggestionType, targetBlock) {
        if (!targetBlock || !targetBlock.parentNode) return;
        this.hideSuggestionPopup();

        if (suggestionType === 'next_sequence_shot') {
            const prev = targetBlock.previousElementSibling;
            targetBlock.remove();
            this.createNextSequenceShot(prev);
            return;
        }

        if (suggestionType === 'end_sequence') {
            const prev = targetBlock.previousElementSibling;
            targetBlock.remove();
            this.endCurrentSequence(prev);
            return;
        }

        this.activeElementBlock = targetBlock;
        if (suggestionType === 'parenthetical') {
            this.setElementType(targetBlock, 'parenthetical');
            const ed = targetBlock.querySelector('.element-content');
            if (ed) {
                ed.innerText = '()';
                ed.focus();
                this.setCursorInsideParenthetical(ed);
            }
        } else {
            this.setElementType(targetBlock, suggestionType);
            const ed = targetBlock.querySelector('.element-content:not(.d-none)') || targetBlock.querySelector('.element-content');
            if (ed) {
                ed.focus();
                this.setCursorToStart(ed);
            }
        }
        this.updateActiveToolbarButton(suggestionType);
        if (this.currentTypeEl) {
            this.currentTypeEl.innerText = this.formatTypeLabel(suggestionType);
        }
        this.markDirty();
        this.calculateLiveStats();
    }

    setCursorInsideParenthetical(el) {
        if (!el) return;
        el.focus();
        if (typeof window.getSelection !== "undefined" && typeof document.createRange !== "undefined") {
            const range = document.createRange();
            const textNode = el.firstChild || el;
            if (textNode.nodeType === Node.TEXT_NODE && textNode.textContent.length >= 2) {
                range.setStart(textNode, 1);
                range.setEnd(textNode, 1);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
            }
        }
    }

    // ----------------------------------------------------
    // SCREENPLAY TEXT PARSER (Batch 2D - Isolated Utility)
    // ----------------------------------------------------
    parseScreenplayText(text, customCharacters = null) {
        if (!text || typeof text !== 'string') return [];

        const normalized = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
        if (!normalized.trim()) return [];

        // Build set of known character names
        const rawChars = customCharacters || this.characters || [];
        const knownCharSet = new Set();
        const knownCharSetLower = new Set();
        rawChars.forEach(c => {
            const name = typeof c === 'string' ? c.trim() : (c && c.name ? String(c.name).trim() : '');
            if (name) {
                knownCharSet.add(name);
                knownCharSetLower.add(name.toLowerCase());
            }
        });

        const sluglineRegex = /^\s*(?:SCENE\s+\d+[:\s—\-]+)?(INT\.?\/EXT\.?|EXT\.?\/INT\.?|INT\.?|EXT\.?|INTERIOR|EXTERIOR|I\/E\.?)\b/i;
        const transitionExact = new Set([
            'CUT TO:', 'FADE IN:', 'FADE OUT:', 'DISSOLVE TO:',
            'SMASH CUT TO:', 'MATCH CUT TO:', 'INTERCUT', 'CUT BACK TO:',
            'FADE TO BLACK:', 'FADE TO BLACK.', 'BACK TO SCENE:',
            'CUT TO', 'FADE IN', 'FADE OUT', 'DISSOLVE TO', 'INTERCUT:',
            'FADE OUT.', 'FADE IN.', 'CUT TO.', 'DISSOLVE TO.'
        ]);
        const seqMarkerExact = new Set([
            'SONG BEGINS', 'MONTAGE BEGINS', 'SONG ENDS', 'MONTAGE ENDS',
            'SONG BEGINS:', 'MONTAGE BEGINS:', 'SONG ENDS:', 'MONTAGE ENDS:'
        ]);
        const numberedShotRegex = /^\s*(\d+)\.\s+(INT\.?\/EXT\.?|EXT\.?\/INT\.?|INT\.?|EXT\.?|INTERIOR|EXTERIOR|I\/E\.?)\b/i;

        const formatParen = (p) => {
            if (typeof this.formatParenthetical === 'function') {
                return this.formatParenthetical(p);
            }
            let trimmed = (p || '').trim();
            while ((trimmed.startsWith('(') && trimmed.endsWith(')')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
                trimmed = trimmed.slice(1, -1).trim();
            }
            return trimmed ? `(${trimmed})` : '';
        };

        const isExplicitParenthetical = (str) => {
            if (!str) return false;
            const t = str.trim();
            return (t.startsWith('(') && t.endsWith(')') && t.length >= 2) ||
                   (t.startsWith('[') && t.endsWith(']') && t.length >= 2);
        };

        // Direction words / participles that can act as parentheticals without parentheses
        const isBareParentheticalWord = (str) => {
            if (!str) return false;
            const t = str.trim();
            if (t.length === 0 || t.length > 35) return false;
            if (/[.?!;]$/.test(t)) return false;
            // Malayalam direction patterns: -ത്തോടെ, -കൊണ്ട്, -ആയി, നിശബ്ദത, etc.
            if (/[\u0D00-\u0D7F]/.test(t)) {
                return /(?:ത്തോടെ|ത്തോട്|കൊണ്ട്|ക്കൊണ്ട്|ആയി|നിശബ്ദത|ഇടവേള|ചിരിയോടെ|ദേഷ്യത്തോടെ|കരച്ചിലോടെ|സംശയത്തോടെ|സ്നേഹത്തോടെ|ഭയത്തോടെ|സങ്കടത്തോടെ|ആശ്ചര്യത്തോടെ|ചിരിച്ചുകൊണ്ട്|കരഞ്ഞുകൊണ്ട്|മന്ത്രിച്ചുകൊണ്ട്|നോക്കിക്കൊണ്ട്|നടന്നുകൊണ്ട്|ഓർത്തു)$/.test(t);
            }
            // English direction patterns: participles ending in -ing, beat, pause, softly, etc.
            const lower = t.toLowerCase();
            const knownEnglishDirections = new Set([
                'beat', 'pause', 'whispering', 'smiling', 'laughing', 'crying', 'sighs', 'sighing',
                'softly', 'gently', 'angrily', 'quietly', 'loudly', 'shouting', 'screaming',
                'hesitant', 'sarcastic', 'surprised', 'confused', 'nodding', 'looking up',
                'looking away', 'turning', 'turning around', 'to himself', 'to herself',
                'into phone', 'over phone', 'continuing', 'stopping'
            ]);
            if (knownEnglishDirections.has(lower)) return true;
            if (/^[a-z]+ing$/i.test(t) && t.length <= 20) return true;
            return false;
        };

        const isDisallowedForCharacter = (clean) => {
            if (!clean || clean.length === 0 || clean.length > 40) return true;
            if (sluglineRegex.test(clean)) return true;
            if (transitionExact.has(clean.toUpperCase()) || clean.toUpperCase().endsWith(' TO:')) return true;
            if (seqMarkerExact.has(clean.toUpperCase()) || numberedShotRegex.test(clean)) return true;
            if (/^\s*\d+[\.\)]\s+/.test(clean)) return true;
            if (isExplicitParenthetical(clean)) return true;
            if (clean.startsWith('[[') && clean.endsWith(']]')) return true;
            if (/^(CHAPTER|PART|ACT|SCENE)\b/i.test(clean)) return true;
            if (/^(NOTE|NOTICE|WARNING|CAUTION)\b/i.test(clean)) return true;
            return false;
        };

        const isNarrativeReporting = (str) => {
            if (!str) return false;
            return /(?:said|asked|replied|shouted|whispered|screamed|told|continued|added|yelled|cried)\b/i.test(str) ||
                   /(?:ചോദിച്ചു|പറഞ്ഞു|തുടങ്ങി|വിളിച്ചു|ഓർത്തു|നോക്കി|നടന്നു|കണ്ടു|നിന്നു|പോയി|വന്നു|ഉത്തരം നൽകി|മറുപടി നൽകി|അറിയിച്ചു)$/.test(str.trim());
        };

        const isCharacterExtension = (bracketContent) => {
            if (!bracketContent) return false;
            let inner = bracketContent.replace(/^[(\[]|[)\]]$/g, '').trim().toUpperCase();
            const knownExtensions = new Set([
                'V.O.', 'VO', 'V.O', 'O.S.', 'OS', 'O.S', 'O.C.', 'OC',
                "CONT'D", 'CONTD', 'CONTINUED',
                'ON PHONE', 'OVER PHONE', 'INTO PHONE', 'PHONE',
                'FILTERED', 'PRE-LAP', 'OFF-SCREEN', 'OFF SCREEN',
                'IN BACKGROUND', 'UNDER BREATH'
            ]);
            if (knownExtensions.has(inner)) return true;
            let innerRaw = bracketContent.replace(/^[(\[]|[)\]]$/g, '').trim();
            if (/^(?:വോയ്സ്\s*ഓവർ|വോയിസ്\s*ഓവർ|ഫോണിൽ|ശബ്ദം|തുടരുന്നു|തുടർന്ന്|ഓഫ്\s*സ്ക്രീൻ)$/.test(innerRaw)) {
                return true;
            }
            return false;
        };

        const isNarrativeActionLine = (str) => {
            if (!str) return false;
            const t = str.trim();
            if (t.length === 0) return false;

            // Common English narrative starters
            if (/^(?:The|A|An|He|She|They|It|His|Her|Their)\s+[A-Za-z]/i.test(t)) {
                return true;
            }

            // Malayalam narrative starters: അവൻ, അവൾ, അവർ, അയാൾ, ഇത്, അത്, etc.
            if (/^(?:അവൻ|അവൾ|അവർ|അയാൾ|ഇവൻ|ഇവൾ|ഇവർ|ആ|ഈ)\s+/i.test(t)) {
                return true;
            }

            // Malayalam narrative action endings (verbs in present/past tense)
            if (/(?:നടക്കുന്നു|നോക്കുന്നു|പോകുന്നു|വരുന്നു|ഇരിക്കുന്നു|നിൽക്കുന്നു|തുടങ്ങുന്നു|എടുക്കുന്നു|കൊടുക്കുന്നു|തുറക്കുന്നു|അടയ്ക്കുന്നു|ചിരിക്കുന്നു|കരയുന്നു|ഓടുന്നു|നടന്നു|നോക്കി|പോയി|വന്നു|ഇരുന്നു|നിന്നു|കണ്ടു|തുറന്നു|അടച്ചു|ചിരിച്ചു|കരഞ്ഞു|ഓടി|എടുത്തു|കൊടുത്തു|പറഞ്ഞു|ചോദിച്ചു)\.?$/.test(t)) {
                return true;
            }

            // English sentences with action verbs ending in sentence punctuation
            if (/[.?!]$/.test(t)) {
                if (/\b(?:walks|walked|steps|stepped|turns|turned|looks|looked|runs|ran|opens|opened|closes|closed|sits|sat|stands|stood|takes|took|moves|moved|enters|entered|leaves|left|picks|picked|drops|dropped|stares|stared|smiles|smiled|cries|cried|screams|screamed|shouts|shouted|gazes|gazed|approaches|approached)\b/i.test(t)) {
                    return true;
                }
            }

            return false;
        };

        const extractBaseName = (clean) => {
            if (!clean) return '';
            let withoutColon = clean.replace(/:$/, '').trim();
            let baseName = withoutColon.replace(/\s*\([^)]*\)\s*$/, '').replace(/\s*\[[^\]]*\]\s*$/, '').trim();
            return baseName;
        };

        const isPlausibleCharacterCandidate = (rawText) => {
            if (!rawText) return false;
            let clean = rawText.trim();
            if (isDisallowedForCharacter(clean)) return false;

            let withoutColon = clean.replace(/:$/, '').trim();
            let baseName = extractBaseName(withoutColon);
            if (!baseName || baseName.length > 40) return false;
            if (/[.?!,;]$/.test(baseName) || isNarrativeReporting(baseName)) return false;

            // Disallow common document, email, and meeting prefixes
            if (/^(agenda|meeting|subject|topic|item|chapter|part|act|section|notice|warning|rule|step|instruction|summary|email|from|to|date|time|location|project|status|review|notes?|tasks?)\b/i.test(baseName)) {
                return false;
            }
            if (/^(അധ്യായം|ഭാഗം|കുറിപ്പ്|വിഷയം|തീരുമാനം)\b/.test(baseName)) {
                return false;
            }

            const words = baseName.split(/\s+/).filter(Boolean);
            if (words.length > 4) return false;

            // Malayalam candidate: 1-4 words, Malayalam script
            if (/[\u0D00-\u0D7F]/.test(baseName)) {
                return true;
            }

            // English candidate
            const hasLetters = /[A-Za-z]/.test(baseName);
            if (!hasLetters) return false;

            // English ALL-CAPS: e.g. "JOHN", "OFFICER 1"
            const isAllUpper = baseName === baseName.toUpperCase() && !/[a-z]/.test(baseName);
            if (isAllUpper) return true;

            // English Title Case / Capitalized: each word must start with an uppercase letter
            // Disallow lowercase words like "agenda for tomorrow"
            const isTitleCased = words.every(w => /^[A-Z]/.test(w) || /^(of|the|de|van|von|la|bin|al)$/i.test(w));
            if (isTitleCased && /^[A-Z]/.test(words[0])) {
                if (/^(Then|Suddenly|After|Meanwhile|However|Because|Although|When|While|And|But|So|There|Here)\b/i.test(baseName)) {
                    return false;
                }
                return true;
            }

            return false;
        };

        // Tokenize raw lines while expanding inline "CHARACTER: DIALOGUE" lines if appropriate
        const rawLines = normalized.split('\n');
        const lines = [];
        let hadBlank = true;

        for (let idx = 0; idx < rawLines.length; idx++) {
            const raw = rawLines[idx].trim();
            if (raw === '') {
                hadBlank = true;
                continue;
            }

            // Check for inline "CHARACTER: DIALOGUE" (e.g. "രാഹുൽ: നീ എവിടെ പോകുന്നു?" or "JOHN: What are you doing?")
            const inlineColonMatch = raw.match(/^([^\n:]{1,35}):\s+(.+)$/);
            if (inlineColonMatch &&
                !sluglineRegex.test(raw) &&
                !transitionExact.has(raw.toUpperCase()) &&
                !seqMarkerExact.has(raw.toUpperCase()) &&
                !numberedShotRegex.test(raw) &&
                !/^\s*\d+[\.\)]\s+/.test(raw) &&
                !raw.startsWith('[[') &&
                !/^(https?|ftp|mailto):/i.test(raw)) {

                const possibleName = inlineColonMatch[1].trim();
                const possibleDialogue = inlineColonMatch[2].trim();

                if (isPlausibleCharacterCandidate(possibleName)) {
                    lines.push({ text: possibleName, afterBlank: hadBlank });
                    lines.push({ text: possibleDialogue, afterBlank: false });
                    hadBlank = false;
                    continue;
                }
            }

            lines.push({ text: raw, afterBlank: hadBlank });
            hadBlank = false;
        }

        if (lines.length === 0) return [];

        // Discovery Pass: multi-pass discovery of character cues in the input text
        const discoveredCharSet = new Set();
        const discoveredCharSetLower = new Set();

        const addDiscoveredChar = (name) => {
            if (!name) return;
            const clean = name.trim();
            if (clean.length > 0 && clean.length <= 40) {
                discoveredCharSet.add(clean);
                discoveredCharSetLower.add(clean.toLowerCase());
            }
        };

        for (let idx = 0; idx < lines.length; idx++) {
            const curText = lines[idx].text;
            if (isDisallowedForCharacter(curText)) continue;

            let withoutColon = curText.replace(/:$/, '').trim();
            let baseName = extractBaseName(curText);
            if (!baseName || /[.?!,;]$/.test(baseName) || isNarrativeReporting(baseName)) continue;

            // 1. Explicit known character
            if (knownCharSet.has(baseName) || knownCharSetLower.has(baseName.toLowerCase())) {
                addDiscoveredChar(baseName);
                continue;
            }

            // 2. Character extension
            if (/\((?:V\.O\.|O\.S\.|CONT'D|ON PHONE|OFF SCREEN)\)/i.test(withoutColon) ||
                /\((?:വോയ്സ്\s*ഓവർ|ഫോണിൽ|ശബ്ദം)\)/i.test(withoutColon)) {
                addDiscoveredChar(baseName);
                continue;
            }

            // Must be plausible character candidate
            if (!isPlausibleCharacterCandidate(curText)) continue;

            // 3. Followed by next non-empty element
            const nextObj = idx + 1 < lines.length ? lines[idx + 1] : null;
            if (nextObj) {
                const nextT = nextObj.text;

                // Parenthetical follower
                if (isExplicitParenthetical(nextT) || isBareParentheticalWord(nextT)) {
                    addDiscoveredChar(baseName);
                    continue;
                }

                // Trailing colon
                if (curText.endsWith(':')) {
                    addDiscoveredChar(baseName);
                    continue;
                }

                // Standalone plausible character cue followed by plausible dialogue line
                if (!isDisallowedForCharacter(nextT)) {
                    addDiscoveredChar(baseName);
                    continue;
                }
            }
        }

        const isCharacterLine = (line, nextLine) => {
            if (!line) return false;
            let clean = line.trim();
            if (isDisallowedForCharacter(clean)) return false;

            let withoutColon = clean.replace(/:$/, '').trim();
            let baseName = extractBaseName(clean);
            if (!baseName || /[.?!,;]$/.test(baseName) || isNarrativeReporting(baseName)) return false;

            // 1. Matches known or discovered character
            if (knownCharSet.has(baseName) || knownCharSetLower.has(baseName.toLowerCase()) ||
                discoveredCharSet.has(baseName) || discoveredCharSetLower.has(baseName.toLowerCase())) {
                return true;
            }

            // 2. Extension match
            if (/\((?:V\.O\.|O\.S\.|CONT'D|ON PHONE|OFF SCREEN)\)/i.test(withoutColon) ||
                /\((?:വോയ്സ്\s*ഓവർ|ഫോണിൽ|ശബ്ദം)\)/i.test(withoutColon)) {
                return true;
            }

            // Must be plausible character candidate
            if (!isPlausibleCharacterCandidate(clean)) return false;

            // 3. Trailing colon
            if (clean.endsWith(':') && nextLine && !isDisallowedForCharacter(nextLine)) {
                return true;
            }

            // 4. Followed by parenthetical or dialogue
            if (nextLine && (isExplicitParenthetical(nextLine) || isBareParentheticalWord(nextLine) || !isDisallowedForCharacter(nextLine))) {
                return true;
            }

            return false;
        };

        const elements = [];
        let i = 0;

        while (i < lines.length) {
            const lineObj = lines[i];
            const text = lineObj.text;
            const uc = text.toUpperCase();
            const nextLineObj = i + 1 < lines.length ? lines[i + 1] : null;
            const nextText = nextLineObj ? nextLineObj.text : null;

            // 1. Note: [[ ... ]]
            if (text.startsWith('[[') && text.endsWith(']]')) {
                elements.push({ type: 'note', content: text.slice(2, -2).trim() });
                i++;
                continue;
            }

            // 2. Sequence markers: SONG BEGINS, MONTAGE BEGINS, etc.
            if (seqMarkerExact.has(uc)) {
                elements.push({ type: 'shot', content: uc.replace(':', '').trim() });
                i++;
                continue;
            }

            // 3. Numbered shots: 1. INT. LOCATION - DAY
            if (numberedShotRegex.test(text)) {
                elements.push({ type: 'shot', content: text });
                i++;
                continue;
            }

            // 4. Scene heading / Slugline
            if (sluglineRegex.test(text)) {
                elements.push({ type: 'scene_heading', content: text });
                i++;
                continue;
            }

            // 5. Transition: CUT TO:, FADE OUT., etc.
            if (transitionExact.has(uc) || (uc.endsWith(' TO:') && uc.length <= 35)) {
                elements.push({ type: 'transition', content: text });
                i++;
                continue;
            }

            // 6. Character line followed by dialogue / parenthetical
            if (isCharacterLine(text, nextText)) {
                let cleanCharName = text.replace(/:$/, '').trim();
                const bracketMatch = cleanCharName.match(/^(.+?)\s*(\([^)\]]+\)|\[[^)\]]+\])\s*$/);
                if (bracketMatch) {
                    const charPart = bracketMatch[1].trim();
                    const bracketPart = bracketMatch[2].trim();
                    if (isCharacterExtension(bracketPart)) {
                        elements.push({ type: 'character', content: `${charPart} ${bracketPart}` });
                    } else {
                        elements.push({ type: 'character', content: charPart });
                        elements.push({ type: 'parenthetical', content: formatParen(bracketPart) });
                    }
                    addDiscoveredChar(extractBaseName(charPart));
                } else {
                    elements.push({ type: 'character', content: cleanCharName });
                    let base = extractBaseName(cleanCharName);
                    addDiscoveredChar(base);
                }
                i++;

                // Optional parenthetical immediately following character
                while (i < lines.length) {
                    const candidateParen = lines[i].text;
                    const nextAfterParen = i + 1 < lines.length ? lines[i + 1].text : null;
                    if (isExplicitParenthetical(candidateParen)) {
                        elements.push({ type: 'parenthetical', content: formatParen(candidateParen) });
                        i++;
                    } else if (nextAfterParen && isBareParentheticalWord(candidateParen)) {
                        elements.push({ type: 'parenthetical', content: formatParen(candidateParen) });
                        i++;
                    } else {
                        break;
                    }
                }

                // Following line(s) are dialogue
                const dialogueLines = [];
                while (i < lines.length) {
                    const dLine = lines[i].text;
                    const dUc = dLine.toUpperCase();
                    const dNext = i + 1 < lines.length ? lines[i + 1].text : null;

                    // Stop condition: next element is heading, sequence marker, transition, or new character
                    if (sluglineRegex.test(dLine) || seqMarkerExact.has(dUc) ||
                        transitionExact.has(dUc) || (dUc.endsWith(' TO:') && dUc.length <= 35) ||
                        numberedShotRegex.test(dLine) || isCharacterLine(dLine, dNext)) {
                        break;
                    }

                    // Parenthetical inside dialogue block
                    if (isExplicitParenthetical(dLine)) {
                        if (dialogueLines.length > 0) {
                            elements.push({ type: 'dialogue', content: dialogueLines.join('\n') });
                            dialogueLines.length = 0;
                        }
                        elements.push({ type: 'parenthetical', content: formatParen(dLine) });
                        i++;
                        continue;
                    } else if (dNext && isBareParentheticalWord(dLine)) {
                        if (dialogueLines.length > 0) {
                            elements.push({ type: 'dialogue', content: dialogueLines.join('\n') });
                            dialogueLines.length = 0;
                        }
                        elements.push({ type: 'parenthetical', content: formatParen(dLine) });
                        i++;
                        continue;
                    }

                    // Stop condition on blank line: blank line indicates end of this dialogue turn
                    if (lines[i].afterBlank && dialogueLines.length > 0) {
                        break;
                    }

                    // Stop condition on action narrative sentence following dialogue
                    if (dialogueLines.length > 0 && isNarrativeActionLine(dLine)) {
                        break;
                    }

                    dialogueLines.push(dLine);
                    i++;
                }

                if (dialogueLines.length > 0) {
                    elements.push({ type: 'dialogue', content: dialogueLines.join('\n') });
                }
                continue;
            }

            // 7. Isolated parenthetical
            if (isExplicitParenthetical(text)) {
                const lastType = elements.length > 0 ? elements[elements.length - 1].type : null;
                if (lastType === 'character' || lastType === 'dialogue') {
                    elements.push({ type: 'parenthetical', content: formatParen(text) });
                    i++;
                    continue;
                }
            }

            // 8. Action: collect consecutive action lines within paragraph
            const actionLines = [text];
            i++;
            while (i < lines.length) {
                if (lines[i].afterBlank) {
                    break;
                }
                const aLine = lines[i].text;
                const aUc = aLine.toUpperCase();
                const aNext = i + 1 < lines.length ? lines[i + 1].text : null;

                if (sluglineRegex.test(aLine) || seqMarkerExact.has(aUc) ||
                    transitionExact.has(aUc) || (aUc.endsWith(' TO:') && aUc.length <= 35) ||
                    numberedShotRegex.test(aLine) || isCharacterLine(aLine, aNext) ||
                    (aLine.startsWith('[[') && aLine.endsWith(']]'))) {
                    break;
                }
                actionLines.push(aLine);
                i++;
            }

            elements.push({ type: 'action', content: actionLines.join('\n') });
        }

        return elements;
    }

    // ----------------------------------------------------
    // SEMANTIC CLIPBOARD & FULL SCENE COPY ENGINE (Batch 1)
    // ----------------------------------------------------
    bindClipboardEvents() {
        document.addEventListener('copy', (e) => this.handleCopy(e));
        document.addEventListener('paste', (e) => this.handlePaste(e));
    }

    escapeAttribute(str) {
        if (!str) return '';
        return str
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    unescapeAttribute(str) {
        if (!str) return '';
        return str
            .replace(/&quot;/g, '"')
            .replace(/&#39;/g, "'")
            .replace(/&lt;/g, '<')
            .replace(/&gt;/g, '>')
            .replace(/&amp;/g, '&');
    }

    formatElementsToPlainText(elements) {
        if (!elements || !elements.length) return '';
        const lines = [];
        elements.forEach(el => {
            const type = el.type || 'action';
            const content = el.content || '';
            if (type === 'scene_heading') {
                lines.push(content + '\n');
            } else if (type === 'character') {
                lines.push('                    ' + content + '\n');
            } else if (type === 'parenthetical') {
                lines.push('                ' + this.formatParenthetical(content) + '\n');
            } else if (type === 'dialogue') {
                lines.push('            ' + content + '\n');
            } else if (type === 'transition') {
                lines.push('                                                    ' + content + '\n');
            } else if (type === 'note') {
                lines.push('[[ ' + content + ' ]]\n');
            } else {
                lines.push(content + '\n');
            }
        });
        return lines.join('\n').trim();
    }

    formatElementsToHtml(elements) {
        if (!elements || !elements.length) return '';
        return elements.map(el => {
            const type = el.type || 'action';
            const content = el.content || '';
            const escaped = this.escapeAttribute(content);
            return `<div data-element-type="${type}" class="kadhascript-element element-type-${type}">${escaped}</div>`;
        }).join('\n');
    }

    isBlockFullySelected(block, range) {
        if (!block || !range) return false;

        if (block.dataset && block.dataset.type === 'scene_heading') {
            // For scene heading in edit mode with builder:
            // If selection is inside heading-location-input, it is partial text of the location
            if (block.querySelector('.scene-heading-builder')) {
                const locInput = block.querySelector('.heading-location-input');
                if (locInput && (document.activeElement === locInput || locInput.contains(range.startContainer))) {
                    return false;
                }
            }
        }

        const ed = block.querySelector('.element-content:not(.d-none)') ||
                   block.querySelector('.element-content, .read-scene-identifier, .heading-location-input');
        if (!ed) return false;

        if (ed.tagName === 'INPUT' || ed.tagName === 'TEXTAREA') {
            const start = ed.selectionStart ?? 0;
            const end = ed.selectionEnd ?? ed.value.length;
            return (start === 0 && end === ed.value.length);
        }

        let hasBefore = false;
        try {
            if (ed.contains(range.startContainer)) {
                const preRange = document.createRange();
                preRange.setStart(ed, 0);
                preRange.setEnd(range.startContainer, range.startOffset);
                hasBefore = preRange.toString().length > 0;
            } else {
                hasBefore = (range.comparePoint(ed, 0) < 0);
            }
        } catch (err) {
            hasBefore = true;
        }

        let hasAfter = false;
        try {
            if (ed.contains(range.endContainer)) {
                const postRange = document.createRange();
                postRange.setStart(range.endContainer, range.endOffset);
                postRange.setEnd(ed, ed.childNodes.length);
                hasAfter = postRange.toString().length > 0;
            } else {
                hasAfter = (range.comparePoint(ed, ed.childNodes.length) > 0);
            }
        } catch (err) {
            hasAfter = true;
        }

        return !hasBefore && !hasAfter;
    }

    extractBlockPartialText(block, range, isFirst, isLast) {
        if (!block || !range) return '';

        const ed = block.querySelector('.element-content:not(.d-none)') ||
                   block.querySelector('.element-content, .read-scene-identifier, .heading-location-input');
        if (!ed) return '';

        if (ed.tagName === 'INPUT' || ed.tagName === 'TEXTAREA') {
            const start = ed.selectionStart ?? 0;
            const end = ed.selectionEnd ?? ed.value.length;
            return ed.value.substring(start, end);
        }

        try {
            const subRange = document.createRange();
            if (isFirst && ed.contains(range.startContainer)) {
                subRange.setStart(range.startContainer, range.startOffset);
            } else {
                subRange.setStart(ed, 0);
            }

            if (isLast && ed.contains(range.endContainer)) {
                subRange.setEnd(range.endContainer, range.endOffset);
            } else {
                subRange.setEnd(ed, ed.childNodes.length);
            }
            return subRange.toString();
        } catch (err) {
            return '';
        }
    }

    handleCopy(e) {
        const activeEl = document.activeElement;
        if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA')) {
            this.lastCopiedPayload = null;
            return;
        }

        const sel = window.getSelection();
        if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return;

        const range = sel.getRangeAt(0);

        // Check if selection is within the screenplay editor content
        const isInsideEdit = this.pageContainer && (this.pageContainer.contains(range.startContainer) || this.pageContainer.contains(range.endContainer));
        const isInsideRead = this.readModeContainer && (this.readModeContainer.contains(range.startContainer) || this.readModeContainer.contains(range.endContainer));

        if (!isInsideEdit && !isInsideRead) return;

        let elements = [];

        if (isInsideEdit) {
            const allBlocks = Array.from(this.pageContainer.querySelectorAll('.script-element-block'));
            const selectedBlocks = allBlocks.filter(block => {
                try {
                    return range.intersectsNode(block);
                } catch (err) {
                    return false;
                }
            });

            if (selectedBlocks.length === 0) return;

            // Check if this is a complete-block selection or a partial-text selection
            const isComplete = selectedBlocks.every(block => this.isBlockFullySelected(block, range));

            if (!isComplete) {
                const parts = selectedBlocks.map((block, idx) => {
                    return this.extractBlockPartialText(block, range, idx === 0, idx === selectedBlocks.length - 1);
                });
                const partialText = parts.join('\n');

                this.lastCopiedPayload = null;

                if (e.clipboardData) {
                    e.preventDefault();
                    e.clipboardData.setData('text/plain', partialText);
                }
                return;
            }

            selectedBlocks.forEach(block => {
                let type = block.dataset.type || 'action';
                let content = '';
                if (type === 'scene_heading') {
                    const intext = block.querySelector('.heading-intext-select')?.value || 'INT.';
                    const loc = block.querySelector('.heading-location-input')?.value.trim() || '';
                    const time = block.querySelector('.heading-time-select')?.value || 'DAY';
                    content = this.buildHeading(intext, loc || 'LOCATION', time);
                    if (!content) {
                        content = block.querySelector('.element-content')?.innerText.trim() || 'INT. LOCATION - DAY';
                    }
                } else {
                    const ed = block.querySelector('.element-content:not(.d-none)') || block.querySelector('.element-content');
                    content = ed ? ed.innerText.trim() : '';
                    if (type === 'parenthetical') {
                        content = this.formatParenthetical(content);
                    }
                }
                elements.push({ type, content });
            });
        } else if (isInsideRead) {
            const allReadItems = Array.from(this.readModeContainer.querySelectorAll('.read-scene-heading, .read-element-block'));
            const selectedItems = allReadItems.filter(item => {
                try {
                    return range.intersectsNode(item);
                } catch (err) {
                    return false;
                }
            });

            if (selectedItems.length === 0) return;

            const isComplete = selectedItems.every(item => this.isBlockFullySelected(item, range));

            if (!isComplete) {
                const parts = selectedItems.map((item, idx) => {
                    return this.extractBlockPartialText(item, range, idx === 0, idx === selectedItems.length - 1);
                });
                const partialText = parts.join('\n');

                this.lastCopiedPayload = null;

                if (e.clipboardData) {
                    e.preventDefault();
                    e.clipboardData.setData('text/plain', partialText);
                }
                return;
            }

            selectedItems.forEach(item => {
                if (item.classList.contains('read-scene-heading')) {
                    const content = item.querySelector('.read-scene-identifier')?.innerText.trim() || item.innerText.trim();
                    elements.push({ type: 'scene_heading', content });
                } else {
                    let type = 'action';
                    for (const cls of item.classList) {
                        if (cls.startsWith('element-type-')) {
                            type = cls.replace('element-type-', '');
                            break;
                        }
                    }
                    let content = item.querySelector('.element-content')?.innerText.trim() || '';
                    if (type === 'parenthetical') {
                        content = this.formatParenthetical(content);
                    }
                    elements.push({ type, content });
                }
            });
        }

        if (elements.length === 0) return;

        const payload = {
            version: "1.0",
            source: "kadhascript",
            elements: elements
        };

        const jsonString = JSON.stringify(payload);
        const plainText = this.formatElementsToPlainText(elements);
        const htmlText = this.formatElementsToHtml(elements);

        this.lastCopiedPayload = payload;

        if (e.clipboardData) {
            e.preventDefault();
            try {
                e.clipboardData.setData('application/x-kadhascript-elements', jsonString);
            } catch (err) {
                // Ignore if engine restricts custom MIME type
            }
            e.clipboardData.setData('text/plain', plainText);
            const htmlWithData = `<div data-kadhascript-elements="${this.escapeAttribute(jsonString)}">${htmlText}</div>`;
            e.clipboardData.setData('text/html', htmlWithData);
        }
    }

    handlePaste(e) {
        // Only intercept in Edit Mode inside page container
        if (this.editorMode !== 'edit' || !this.pageContainer) return;

        // Do not intercept if active element is a search input or modal input
        const activeEl = document.activeElement;
        if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.closest('.modal'))) {
            if (!activeEl.classList.contains('heading-location-input')) {
                return;
            }
        }

        this.hideSuggestionPopup();
        this.hideAutocomplete();

        let payload = null;
        let rawCustom = e.clipboardData ? e.clipboardData.getData('application/x-kadhascript-elements') : null;
        if (rawCustom) {
            try {
                payload = JSON.parse(rawCustom);
            } catch (err) {
                payload = null;
            }
        }

        // Fallback: check text/html data attribute
        if (!payload && e.clipboardData) {
            const rawHtml = e.clipboardData.getData('text/html');
            if (rawHtml && rawHtml.includes('data-kadhascript-elements=')) {
                try {
                    const match = rawHtml.match(/data-kadhascript-elements=["']([^"']+)["']/);
                    if (match && match[1]) {
                        const unescaped = this.unescapeAttribute(match[1]);
                        payload = JSON.parse(unescaped);
                    }
                } catch (err) {
                    payload = null;
                }
            }
        }

        // In-memory fallback if within same browser session
        if (!payload && this.lastCopiedPayload && e.clipboardData) {
            const pastedText = e.clipboardData.getData('text/plain');
            const expectedText = this.formatElementsToPlainText(this.lastCopiedPayload.elements);
            if (pastedText && expectedText && pastedText.trim() === expectedText.trim()) {
                payload = this.lastCopiedPayload;
            }
        }

        // ----------------------------------------------------
        // BRANCH 1: INTERNAL KADHASCRIPT SEMANTIC CLIPBOARD
        // ----------------------------------------------------
        if (payload && payload.elements && Array.isArray(payload.elements) && payload.elements.length > 0) {
            e.preventDefault();
            const preSnap = this.captureSnapshot();

            // Determine target block
            let targetBlock = this.activeElementBlock;
            if (!targetBlock || !targetBlock.parentNode || targetBlock.parentNode !== this.pageContainer) {
                const sel = window.getSelection();
                if (sel && sel.anchorNode) {
                    const node = sel.anchorNode instanceof Element ? sel.anchorNode : sel.anchorNode.parentElement;
                    targetBlock = node ? node.closest('.script-element-block') : null;
                }
            }
            if (!targetBlock || targetBlock.parentNode !== this.pageContainer) {
                targetBlock = this.pageContainer.querySelector('.script-element-block.focused') ||
                              this.pageContainer.lastElementChild;
            }

            // Check if targetBlock is an empty block that can be safely replaced
            let shouldReplaceTarget = false;
            if (targetBlock && targetBlock.dataset.type !== 'scene_heading') {
                const ed = targetBlock.querySelector('.element-content:not(.d-none)') || targetBlock.querySelector('.element-content');
                if (ed && ed.innerText.trim() === '') {
                    shouldReplaceTarget = true;
                }
            }

            let insertAnchor = targetBlock;
            if (shouldReplaceTarget && targetBlock && targetBlock.previousElementSibling) {
                insertAnchor = targetBlock.previousElementSibling;
            }

            let currentAnchor = insertAnchor;
            let firstInserted = null;
            let lastInserted = null;

            payload.elements.forEach((el) => {
                const type = el.type || 'action';
                let content = el.content || '';
                if (type === 'parenthetical') {
                    content = this.formatParenthetical(content);
                }
                const newBlock = this.createElementBlock(type, content, currentAnchor);
                if (!firstInserted) firstInserted = newBlock;
                lastInserted = newBlock;
                currentAnchor = newBlock;
            });

            if (shouldReplaceTarget && targetBlock && targetBlock.parentNode) {
                targetBlock.remove();
            }

            if (lastInserted) {
                const lastEd = lastInserted.querySelector('.element-content:not(.d-none)') || lastInserted.querySelector('.element-content');
                if (lastEd) {
                    lastEd.focus();
                    this.setCursorToEnd(lastEd);
                }
                document.querySelectorAll('.script-element-block.focused').forEach(b => b.classList.remove('focused'));
                lastInserted.classList.add('focused');
                this.activeElementBlock = lastInserted;
                this.updateActiveToolbarButton(lastInserted.dataset.type);
                if (this.currentTypeEl) {
                    this.currentTypeEl.innerText = this.formatTypeLabel(lastInserted.dataset.type);
                }
            }

            this.pushUndoSnapshot(preSnap);
            this.markDirty();
            this.calculateLiveStats();
            return;
        }

        // ----------------------------------------------------
        // BRANCH 2: EXTERNAL CLIPBOARD
        // ----------------------------------------------------
        let externalText = e.clipboardData ? e.clipboardData.getData('text/plain') : '';
        if (!externalText) {
            // Nothing to paste
            return;
        }

        const preSnap = this.captureSnapshot();

        // Intercept external paste
        e.preventDefault();

        // Normalize line breaks: CRLF and CR -> LF
        externalText = externalText.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

        // Resolve target editable element
        let targetEditable = null;
        const sel = window.getSelection();

        if (sel && sel.anchorNode) {
            const node = sel.anchorNode instanceof Element ? sel.anchorNode : sel.anchorNode.parentElement;
            if (node) {
                const ed = node.closest('.element-content, .heading-location-input');
                if (ed && this.pageContainer.contains(ed)) {
                    targetEditable = ed;
                }
            }
        }

        if (!targetEditable && document.activeElement) {
            const act = document.activeElement;
            if ((act.classList.contains('element-content') || act.classList.contains('heading-location-input')) && this.pageContainer.contains(act)) {
                targetEditable = act;
            }
        }

        let isTargetAlreadyFocused = !!targetEditable;

        if (!targetEditable) {
            // Case C: No contenteditable currently has focus.
            // Resolve safe target block from existing editor state
            let fallbackBlock = this.activeElementBlock;
            if (!fallbackBlock || !this.pageContainer.contains(fallbackBlock)) {
                fallbackBlock = this.pageContainer.querySelector('.script-element-block.focused');
            }
            if (!fallbackBlock || !this.pageContainer.contains(fallbackBlock)) {
                fallbackBlock = this.pageContainer.lastElementChild;
            }

            if (!fallbackBlock || !this.pageContainer.contains(fallbackBlock)) {
                // No valid editing target exists in the editor. Fail safely.
                return;
            }

            targetEditable = fallbackBlock.querySelector('.element-content:not(.d-none)') ||
                             fallbackBlock.querySelector('.element-content, .heading-location-input');

            if (!targetEditable) {
                return;
            }

            // Place caret at a predictable safe location: end of the target element
            targetEditable.focus();
            this.setCursorToEnd(targetEditable);

            // Update focused state on fallback block
            document.querySelectorAll('.script-element-block.focused').forEach(b => b.classList.remove('focused'));
            fallbackBlock.classList.add('focused');
            this.activeElementBlock = fallbackBlock;
            this.updateActiveToolbarButton(fallbackBlock.dataset.type);
            if (this.currentTypeEl) {
                this.currentTypeEl.innerText = this.formatTypeLabel(fallbackBlock.dataset.type);
            }
        }

                const isLocationInput = targetEditable.tagName === 'INPUT' || targetEditable.tagName === 'TEXTAREA' || targetEditable.classList.contains('heading-location-input');
        const isSingleLine = !externalText.includes('\n');

        // Check if external text qualifies for structural screenplay parsing:
        // 1. Must be in a screenplay element (not input/location field)
        // 2. Must be multiline text
        if (!isLocationInput && !isSingleLine) {
            let parsedElements = [];
            try {
                parsedElements = this.parseScreenplayText(externalText);
            } catch (err) {
                parsedElements = [];
            }

            // Must contain at least one screenplay-specific element (not merely action/prose)
            const hasScreenplayElements = parsedElements && parsedElements.length > 0 &&
                                          parsedElements.some(el => el && el.type && el.type !== 'action');

            const VALID_TYPES = new Set(['scene_heading', 'action', 'character', 'dialogue', 'parenthetical', 'transition', 'shot', 'note']);
            const isValidPlan = hasScreenplayElements && parsedElements.every(el => el && el.type && VALID_TYPES.has(el.type));

            if (isValidPlan) {
                const isSequenceScene = !!this.currentSceneIsSequence;
                const headingElements = parsedElements.filter(e => e.type === 'scene_heading');
                const hasMultipleHeadings = headingElements.length > 1;

                let updatedSceneHeading = false;
                const elementsToInsert = [];

                for (let idx = 0; idx < parsedElements.length; idx++) {
                    const el = parsedElements[idx];
                    let type = el.type || 'action';
                    let content = el.content || '';

                    // Context Safety 1: Sequence markers and sequence shots in ordinary scenes
                    if (!isSequenceScene && type === 'shot') {
                        const trimmedShot = (content || '').trim().toUpperCase();
                        if (trimmedShot === 'SONG BEGINS' || trimmedShot === 'MONTAGE BEGINS' ||
                            trimmedShot === 'SONG ENDS' || trimmedShot === 'MONTAGE ENDS' ||
                            /^\s*\d+\.\s+/.test(content)) {
                            type = 'action';
                        }
                    }

                    // Context Safety 2: Scene Headings
                    if (type === 'scene_heading') {
                        if (isSequenceScene) {
                            type = 'action';
                        } else if (hasMultipleHeadings) {
                            type = 'action';
                        } else {
                            const existingHeadingBlock = this.pageContainer.querySelector('.script-element-block[data-type="scene_heading"]');
                            if (existingHeadingBlock) {
                                const locInp = existingHeadingBlock.querySelector('.heading-location-input');
                                const intextSel = existingHeadingBlock.querySelector('.heading-intext-select');
                                const timeSel = existingHeadingBlock.querySelector('.heading-time-select');
                                const ed = existingHeadingBlock.querySelector('.element-content');

                                if (locInp && (!locInp.value.trim() || locInp.value.trim() === 'LOCATION') && idx === 0) {
                                    const parsed = this.parseHeading(content);
                                    if (intextSel) intextSel.value = parsed.intext;
                                    if (locInp) locInp.value = parsed.location;
                                    if (timeSel) timeSel.value = parsed.time;
                                    if (ed) ed.innerText = this.buildHeading(parsed.intext, parsed.location, parsed.time);
                                    this.currentSceneHeading = ed ? ed.innerText : content;
                                    updatedSceneHeading = true;
                                    continue;
                                } else {
                                    type = 'action';
                                }
                            }
                        }
                    }

                    elementsToInsert.push({ type, content });
                }

                if (elementsToInsert.length === 0 && updatedSceneHeading) {
                    this.pushUndoSnapshot(preSnap);
                    this.markDirty();
                    this.calculateLiveStats();
                    return;
                }

                if (elementsToInsert.length > 0) {
                    let targetBlock = targetEditable.closest('.script-element-block');
                    if (!targetBlock || targetBlock.parentNode !== this.pageContainer) {
                        targetBlock = this.activeElementBlock || this.pageContainer.lastElementChild;
                    }

                    let shouldReplaceTarget = false;
                    if (targetBlock && targetBlock.dataset.type !== 'scene_heading') {
                        const ed = targetBlock.querySelector('.element-content:not(.d-none)') || targetBlock.querySelector('.element-content');
                        if (ed && ed.innerText.trim() === '') {
                            shouldReplaceTarget = true;
                        }
                    }

                    let insertAnchor = targetBlock;
                    if (shouldReplaceTarget && targetBlock && targetBlock.previousElementSibling) {
                        insertAnchor = targetBlock.previousElementSibling;
                    }

                    const targetBlockNextSibling = shouldReplaceTarget && targetBlock ? targetBlock.nextSibling : null;
                    let targetBlockRemoved = false;

                    let currentAnchor = insertAnchor;
                    let firstInserted = null;
                    let lastInserted = null;
                    const insertedBlocks = [];

                    try {
                        for (let k = 0; k < elementsToInsert.length; k++) {
                            const item = elementsToInsert[k];
                            let cType = item.type || 'action';
                            let cContent = item.content || '';
                            if (cType === 'parenthetical') {
                                cContent = this.formatParenthetical(cContent);
                            }
                            const newBlock = this.createElementBlock(cType, cContent, currentAnchor);
                            insertedBlocks.push(newBlock);
                            if (!firstInserted) firstInserted = newBlock;
                            lastInserted = newBlock;
                            currentAnchor = newBlock;
                        }

                        if (shouldReplaceTarget && targetBlock && targetBlock.parentNode) {
                            targetBlock.remove();
                            targetBlockRemoved = true;
                        }

                        if (lastInserted) {
                            const lastEd = lastInserted.querySelector('.element-content:not(.d-none)') || lastInserted.querySelector('.element-content');
                            if (lastEd) {
                                lastEd.focus();
                                this.setCursorToEnd(lastEd);
                            }
                            document.querySelectorAll('.script-element-block.focused').forEach(b => b.classList.remove('focused'));
                            lastInserted.classList.add('focused');
                            this.activeElementBlock = lastInserted;
                            this.updateActiveToolbarButton(lastInserted.dataset.type);
                            if (this.currentTypeEl) {
                                this.currentTypeEl.innerText = this.formatTypeLabel(lastInserted.dataset.type);
                            }
                        }

                        this.pushUndoSnapshot(preSnap);
                        this.markDirty();
                        this.calculateLiveStats();
                        return;
                    } catch (insertionErr) {
                        // Rollback any partially inserted blocks
                        insertedBlocks.forEach(b => {
                            if (b && b.parentNode) b.remove();
                        });

                        // Restore original destination block if it was removed
                        if (targetBlockRemoved && targetBlock && !targetBlock.parentNode) {
                            if (targetBlockNextSibling && targetBlockNextSibling.parentNode === this.pageContainer) {
                                this.pageContainer.insertBefore(targetBlock, targetBlockNextSibling);
                            } else {
                                this.pageContainer.appendChild(targetBlock);
                            }
                            document.querySelectorAll('.script-element-block.focused').forEach(b => b.classList.remove('focused'));
                            targetBlock.classList.add('focused');
                            this.activeElementBlock = targetBlock;
                            if (targetEditable) {
                                targetEditable.focus();
                                this.setCursorToEnd(targetEditable);
                            }
                            this.updateActiveToolbarButton(targetBlock.dataset.type);
                            if (this.currentTypeEl) {
                                this.currentTypeEl.innerText = this.formatTypeLabel(targetBlock.dataset.type);
                            }
                        }
                        // Fall back to clean inline plain-text paste below
                    }
                }
            }
        }

// Insert clean plain text at current caret position
        this.insertPlainTextAtCaret(targetEditable, externalText, isTargetAlreadyFocused);

        this.pushUndoSnapshot(preSnap);
        this.markDirty();
        this.calculateLiveStats();
    }

    insertPlainTextAtCaret(targetEditable, text, isTargetAlreadyFocused) {
        if (!targetEditable || !text) return;

        if (targetEditable.tagName === 'INPUT' || targetEditable.tagName === 'TEXTAREA') {
            const start = targetEditable.selectionStart ?? targetEditable.value.length;
            const end = targetEditable.selectionEnd ?? targetEditable.value.length;
            const val = targetEditable.value;
            const cleanText = text.replace(/\n/g, ' ');
            targetEditable.value = val.slice(0, start) + cleanText + val.slice(end);
            targetEditable.selectionStart = targetEditable.selectionEnd = start + cleanText.length;
            targetEditable.dispatchEvent(new Event('input', { bubbles: true }));
            return;
        }

        if (!isTargetAlreadyFocused) {
            targetEditable.focus();
            this.setCursorToEnd(targetEditable);
        }

        let inserted = false;
        try {
            inserted = document.execCommand('insertText', false, text);
        } catch (e) {
            inserted = false;
        }

        if (!inserted) {
            const sel = window.getSelection();
            if (sel && sel.rangeCount > 0) {
                let range = sel.getRangeAt(0);
                if (!targetEditable.contains(range.commonAncestorContainer)) {
                    range = document.createRange();
                    range.selectNodeContents(targetEditable);
                    range.collapse(false);
                    sel.removeAllRanges();
                    sel.addRange(range);
                }
                range.deleteContents();
                const textNode = document.createTextNode(text);
                range.insertNode(textNode);
                range.setStartAfter(textNode);
                range.setEndAfter(textNode);
                sel.removeAllRanges();
                sel.addRange(range);
            } else {
                targetEditable.appendChild(document.createTextNode(text));
                this.setCursorToEnd(targetEditable);
            }
        }

        targetEditable.dispatchEvent(new Event('input', { bubbles: true }));
    }

    async copyFullScene(sceneId) {
        try {
            const sid = Number(sceneId);
            let sceneHeading = 'INT. LOCATION - DAY';
            let elements = [];
            let transition = 'CUT TO:';

            if (sid === Number(this.currentSceneId)) {
                // Use live editor state
                const payload = this.extractScenePayload();
                sceneHeading = payload.heading || 'INT. LOCATION - DAY';
                transition = this.currentSceneTransition || 'CUT TO:';
                elements = (payload.elements || []).map(e => ({
                    type: e.element_type,
                    content: e.content
                }));
                const endsWithSequence = elements.length > 0 && (() => {
                    for (let i = elements.length - 1; i >= 0; i--) {
                        if (elements[i].type !== 'note') {
                            const c = (elements[i].content || '').trim().toUpperCase();
                            return c === 'SONG ENDS' || c === 'MONTAGE ENDS' || c === 'SONG BEGINS' || c === 'MONTAGE BEGINS';
                        }
                    }
                    return false;
                })();
                const hasTransition = elements.some(e => e.type === 'transition');
                if (!hasTransition && transition && !endsWithSequence) {
                    elements.push({ type: 'transition', content: transition });
                }
            } else {
                // Fetch scene data from existing API
                const res = await fetch(`/scripts/api/${this.scriptId}/scenes/${sid}/`);
                if (!res.ok) throw new Error('Failed to fetch scene data');
                const data = await res.json();
                sceneHeading = data.scene.heading || 'INT. LOCATION - DAY';
                transition = data.scene.transition || 'CUT TO:';
                elements = (data.elements || []).map(e => ({
                    type: e.element_type,
                    content: e.content
                }));
                const endsWithSequence = elements.length > 0 && (() => {
                    for (let i = elements.length - 1; i >= 0; i--) {
                        if (elements[i].type !== 'note') {
                            const c = (elements[i].content || '').trim().toUpperCase();
                            return c === 'SONG ENDS' || c === 'MONTAGE ENDS' || c === 'SONG BEGINS' || c === 'MONTAGE BEGINS';
                        }
                    }
                    return false;
                })();
                const hasTransition = elements.some(e => e.type === 'transition');
                if (!hasTransition && transition && !endsWithSequence) {
                    elements.push({ type: 'transition', content: transition });
                }
            }

            const fullScenePayload = {
                version: "1.0",
                source: "kadhascript",
                is_full_scene: true,
                scene_id: sid,
                scene_heading: sceneHeading,
                elements: elements,
                transition: transition
            };

            const jsonString = JSON.stringify(fullScenePayload);
            const plainText = this.formatElementsToPlainText(elements);
            const htmlText = this.formatElementsToHtml(elements);

            this.lastCopiedPayload = fullScenePayload;

            let writeSuccess = false;
            if (navigator.clipboard && navigator.clipboard.write) {
                try {
                    const textBlob = new Blob([plainText], { type: 'text/plain' });
                    const htmlBlob = new Blob([
                        `<div data-kadhascript-elements="${this.escapeAttribute(jsonString)}">${htmlText}</div>`
                    ], { type: 'text/html' });

                    try {
                        const customBlob = new Blob([jsonString], { type: 'application/x-kadhascript-elements' });
                        await navigator.clipboard.write([
                            new ClipboardItem({
                                'application/x-kadhascript-elements': customBlob,
                                'text/plain': textBlob,
                                'text/html': htmlBlob,
                            })
                        ]);
                        writeSuccess = true;
                    } catch (mErr) {
                        await navigator.clipboard.write([
                            new ClipboardItem({
                                'text/plain': textBlob,
                                'text/html': htmlBlob,
                            })
                        ]);
                        writeSuccess = true;
                    }
                } catch (wErr) {
                    console.warn('Clipboard write failed, falling back to writeText:', wErr);
                }
            }

            if (!writeSuccess && navigator.clipboard && navigator.clipboard.writeText) {
                try {
                    await navigator.clipboard.writeText(plainText);
                    writeSuccess = true;
                } catch (tErr) {
                    console.warn('Clipboard writeText failed:', tErr);
                }
            }

            this.showCopyFeedback('Full scene copied');
        } catch (err) {
            console.error('Error copying full scene:', err);
        }
    }

    showCopyFeedback(message = 'Full scene copied') {
        if (this.saveBadge) {
            const prevText = this.saveBadge.innerHTML;
            const prevClass = this.saveBadge.className;
            this.saveBadge.className = 'save-status-badge saved';
            this.saveBadge.innerHTML = `<i class="bi bi-clipboard-check me-1"></i> ${message} ✓`;
            setTimeout(() => {
                if (!this.isDirty) {
                    this.saveBadge.className = prevClass;
                    this.saveBadge.innerHTML = prevText;
                }
            }, 2000);
        }
    }

    // ====================================================
    // SEQUENCE WORKFLOW (Song & Montage Sequences)
    // ====================================================
    detectCurrentSequenceState(refBlock = null) {
        if (!this.pageContainer) {
            return { inSequence: false, type: null, startBlock: null, shotCount: 0, hasEnded: false, isSequenceScene: false };
        }
        const blocks = Array.from(this.pageContainer.querySelectorAll('.script-element-block'));
        let target = refBlock || this.activeElementBlock;
        if (!target || !this.pageContainer.contains(target)) {
            target = blocks.length > 0 ? blocks[blocks.length - 1] : null;
        }

        let inSequence = Boolean(this.currentSceneIsSequence);
        let sequenceType = this.currentSceneSequenceType || null; // 'song' | 'montage'
        let startBlock = null;
        let shotCount = 0;
        let hasEnded = false;

        for (const block of blocks) {
            const type = block.dataset.type;
            const content = (block.querySelector('.element-content')?.innerText || '').trim().toUpperCase();

            if (type === 'shot') {
                if (content === 'SONG BEGINS' || (block.classList.contains('sequence-marker-start') && content.includes('SONG'))) {
                    inSequence = true;
                    sequenceType = 'song';
                    startBlock = block;
                    shotCount = 0;
                    hasEnded = false;
                } else if (content === 'MONTAGE BEGINS' || (block.classList.contains('sequence-marker-start') && content.includes('MONTAGE'))) {
                    inSequence = true;
                    sequenceType = 'montage';
                    startBlock = block;
                    shotCount = 0;
                    hasEnded = false;
                } else if (content === 'SONG ENDS' || content === 'MONTAGE ENDS' || block.classList.contains('sequence-marker-end')) {
                    hasEnded = true;
                    if (block === target) {
                        return { inSequence: false, type: sequenceType, startBlock, shotCount, justEnded: true, hasEnded: true, isSequenceScene: Boolean(this.currentSceneIsSequence || startBlock) };
                    }
                    inSequence = false;
                    startBlock = null;
                    shotCount = 0;
                } else if (inSequence && (block.classList.contains('sequence-shot-heading') || /^\d+\.\s*/.test(content))) {
                    shotCount++;
                }
            }

            if (block === target) {
                break;
            }
        }

        return {
            inSequence: inSequence && !hasEnded,
            type: sequenceType || (this.currentSceneSequenceType || 'song'),
            startBlock,
            shotCount,
            hasEnded: hasEnded,
            isSequenceScene: Boolean(this.currentSceneIsSequence || startBlock)
        };
    }

    detectSceneSequenceState() {
        return this.detectCurrentSequenceState(null);
    }

    updateSequenceToolbarState() {
        const state = this.detectCurrentSequenceState();
        const btnNext = document.getElementById('btnNextSequenceShot');
        const btnEnd = document.getElementById('btnEndSequence');
        const btnStartSong = document.getElementById('btnStartSongSequence');
        const btnStartMontage = document.getElementById('btnStartMontageSequence');
        const btnDropdown = document.getElementById('btnSequenceDropdown');

        const canAddShot = state.isSequenceScene && !state.hasEnded;
        const canEndSeq = state.isSequenceScene && !state.hasEnded;

        if (btnNext) {
            btnNext.disabled = !canAddShot;
            btnNext.classList.toggle('disabled', !canAddShot);
        }
        if (btnEnd) {
            btnEnd.disabled = !canEndSeq;
            btnEnd.classList.toggle('disabled', !canEndSeq);
            if (canEndSeq && state.type) {
                btnEnd.innerHTML = `<i class="bi bi-stop-circle me-2"></i>End ${state.type === 'montage' ? 'Montage' : 'Song'} Sequence`;
            } else {
                btnEnd.innerHTML = `<i class="bi bi-stop-circle me-2"></i>End Sequence`;
            }
        }
        if (btnStartSong) {
            const disableStart = state.isSequenceScene && !state.hasEnded;
            btnStartSong.disabled = disableStart;
            btnStartSong.classList.toggle('disabled', disableStart);
        }
        if (btnStartMontage) {
            const disableStart = state.isSequenceScene && !state.hasEnded;
            btnStartMontage.disabled = disableStart;
            btnStartMontage.classList.toggle('disabled', disableStart);
        }
        if (btnDropdown) {
            if (state.isSequenceScene) {
                btnDropdown.classList.add('btn-sequence-active');
            } else {
                btnDropdown.classList.remove('btn-sequence-active');
            }
        }
    }

    renumberSequenceShots() {
        if (!this.pageContainer) return;
        const blocks = Array.from(this.pageContainer.querySelectorAll('.script-element-block'));
        let inSeq = Boolean(this.currentSceneIsSequence);
        let counter = 1;

        const montageBlocks = blocks.filter(b => {
            if (b.dataset.type !== 'shot') return false;
            const c = (b.querySelector('.element-content')?.innerText || '').trim().toUpperCase();
            return c === 'MONTAGE BEGINS' || (b.classList.contains('sequence-marker-start') && (b.dataset.sequenceType === 'montage' || c.includes('MONTAGE')));
        });
        const totalMontages = montageBlocks.length;
        const ordinals = ['First', 'Second', 'Third', 'Fourth', 'Fifth', 'Sixth', 'Seventh', 'Eighth', 'Ninth', 'Tenth'];

        montageBlocks.forEach((mBlock, idx) => {
            const tag = mBlock.querySelector('.element-type-tag');
            const label = totalMontages > 1 ? `${ordinals[idx] || (idx + 1)} Montage` : 'Montage';
            mBlock.dataset.sequenceLabel = label;
            if (tag) {
                tag.innerText = label;
            }
        });

        blocks.forEach(block => {
            const type = block.dataset.type;
            const content = (block.querySelector('.element-content')?.innerText || '').trim().toUpperCase();

            if (type === 'shot') {
                if (content === 'SONG BEGINS' || content === 'MONTAGE BEGINS' || block.classList.contains('sequence-marker-start')) {
                    inSeq = true;
                    counter = 1;
                } else if (content === 'SONG ENDS' || content === 'MONTAGE ENDS' || block.classList.contains('sequence-marker-end')) {
                    inSeq = false;
                    counter = 1;
                } else if (inSeq && block.classList.contains('sequence-shot-heading')) {
                    const numSpan = block.querySelector('.sequence-shot-number');
                    if (numSpan) {
                        numSpan.innerText = `${counter}.`;
                    }
                    const editable = block.querySelector('.element-content');
                    const intextSel = block.querySelector('.heading-intext-select');
                    const locInp = block.querySelector('.heading-location-input');
                    const timeSel = block.querySelector('.heading-time-select');
                    if (editable && intextSel && locInp && timeSel) {
                        const built = this.buildHeading(intextSel.value, locInp.value.trim(), timeSel.value);
                        editable.innerText = `${counter}. ${built || `${intextSel.value} ${locInp.value.trim() || 'LOCATION'} - ${timeSel.value}`}`;
                    }
                    counter++;
                }
            }
        });
    }

    async startSequence(sequenceType = 'song') {
        const seqState = this.detectSceneSequenceState();
        if (seqState.inSequence && !seqState.hasEnded) {
            const endMarkerText = seqState.type === 'montage' ? 'MONTAGE ENDS' : 'SONG ENDS';
            const allBlocks = Array.from(this.pageContainer.querySelectorAll('.script-element-block'));
            const lastBlock = allBlocks.length > 0 ? allBlocks[allBlocks.length - 1] : null;
            this.createElementBlock('shot', endMarkerText, lastBlock);
            this.renumberSequenceShots();
            this.updateSequenceToolbarState();
            this.markDirty();
        }

        try {
            await this.flushSave();
        } catch (err) {
            console.error('Save failed before starting sequence:', err);
            alert('Could not save current scene. Sequence creation was cancelled to protect your unsaved writing. Please retry once saved.');
            return;
        }

        try {
            this.setSaveStatus('saving', 'Creating sequence scene...');
            const res = await fetch(`/scripts/api/${this.scriptId}/scenes/sequence/`, {
                method: 'POST',
                headers: this.getHeaders(),
                body: JSON.stringify({
                    reference_scene_id: parseInt(this.currentSceneId),
                    sequence_type: sequenceType
                })
            });
            if (!res.ok) throw new Error('Could not create sequence scene');
            const data = await res.json();

            this.renderScenesTree(data.scenes_tree);
            await this.switchScene(data.scene.id);

            const locInp = this.pageContainer.querySelector('.sequence-shot-heading .heading-location-input') || this.pageContainer.querySelector('.heading-location-input');
            if (locInp) {
                locInp.focus();
                locInp.select();
            }
        } catch (err) {
            alert('Failed to start sequence: ' + err.message);
            this.setSaveStatus('error', 'Error creating sequence');
        }
    }

    createNextSequenceShot(targetBlock = null, forcedNum = null) {
        const preSnap = this.captureSnapshot();
        let insertAfter = targetBlock || this.activeElementBlock;
        if (!insertAfter || !this.pageContainer.contains(insertAfter)) {
            const allBlocks = Array.from(this.pageContainer.querySelectorAll('.script-element-block'));
            insertAfter = allBlocks.length > 0 ? allBlocks[allBlocks.length - 1] : null;
        }

        // Determine next sequence shot number based on existing shot headings
        let nextNum = forcedNum;
        if (!nextNum) {
            const shotBlocks = Array.from(this.pageContainer.querySelectorAll('.sequence-shot-heading'));
            nextNum = shotBlocks.length + 1;
        }

        const newBlock = this.createElementBlock('shot', `${nextNum}. INT. LOCATION - DAY`, insertAfter);

        this.renumberSequenceShots();
        this.updateSequenceToolbarState();
        this.pushUndoSnapshot(preSnap);
        this.markDirty();
        this.calculateLiveStats();

        const locInp = newBlock.querySelector('.heading-location-input');
        if (locInp) {
            locInp.focus();
            locInp.select();
        }
        return newBlock;
    }

    endCurrentSequence(targetBlock = null) {
        const state = this.detectCurrentSequenceState(targetBlock);
        if (state.hasEnded) {
            return null;
        }

        const preSnap = this.captureSnapshot();
        const endMarkerText = state.type === 'montage' ? 'MONTAGE ENDS' : 'SONG ENDS';

        let insertAfter = targetBlock || this.activeElementBlock;
        if (!insertAfter || !this.pageContainer.contains(insertAfter)) {
            const allBlocks = Array.from(this.pageContainer.querySelectorAll('.script-element-block'));
            insertAfter = allBlocks.length > 0 ? allBlocks[allBlocks.length - 1] : null;
        }

        const endBlock = this.createElementBlock('shot', endMarkerText, insertAfter);
        const nextAction = this.createElementBlock('action', '', endBlock);

        this.renumberSequenceShots();
        this.updateSequenceToolbarState();
        this.pushUndoSnapshot(preSnap);
        this.markDirty();
        this.calculateLiveStats();

        const ed = nextAction.querySelector('.element-content');
        if (ed) {
            ed.focus();
            this.setCursorToStart(ed);
        }
        return endBlock;
    }
}
