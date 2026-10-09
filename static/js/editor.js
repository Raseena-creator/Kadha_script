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
        this.sceneSelectModalEl = document.getElementById('editorSceneSelectModal');
        this.bsSceneSelectModal = this.sceneSelectModalEl ? new bootstrap.Modal(this.sceneSelectModalEl) : null;
        this.pendingDeleteSceneId = null;
        this.sceneSelectMode = null;
        this.isCreatingScene = false;

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
        this.editorRoot = document.getElementById('screenplayEditor');
        this.readModeContainer = document.getElementById('readModeContainer');
        this.btnEditFab = document.getElementById('btnEnterEditMode') || document.getElementById('readModeEditButton');
        this.btnDoneFab = document.getElementById('btnExitEditMode') || document.getElementById('readModeDoneButton');
        this.readModeObserver = null;
        this.suggestionPopup = document.getElementById('elementSuggestionPopup');
        this.activeSuggestionBlock = null;
        this.activeSuggestionIndex = -1;
        this.lastCopiedPayload = null;

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
            this.currentMainSceneId = data.scene.parent_scene_id || data.scene.id;
            this.currentSceneIntercutSourceId = data.scene.intercut_source_id || null;
            this.currentSceneIdentifier = data.scene.scene_identifier || (data.scene.is_sub_scene ? 'Scene 1.A' : 'Scene 1');
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
            this.setSaveStatus('saved', 'Saved ✓');
            this.isDirty = false;
            this.needsQueuedSave = false;
            this.changeVersion = 0;
        } catch (err) {
            if (requestId !== this.loadRequestId) {
                return;
            }
            console.error('Error loading scene:', err);
            this.setSaveStatus('error', 'Error loading scene');
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
        this.pageContainer.innerHTML = '';

        const allElements = elements || [];
        const contentElements = allElements.filter(e => e.element_type !== 'note');
        const noteElements = allElements.filter(e => e.element_type === 'note');

        if (contentElements.length === 0) {
            this.createElementBlock('scene_heading', scene.heading || 'INT. LOCATION - DAY');
            this.createElementBlock('action', '');
        } else {
            contentElements.forEach(elem => {
                this.createElementBlock(elem.element_type, elem.content);
            });
        }

        // Render any Notes
        noteElements.forEach(elem => {
            this.createElementBlock(elem.element_type, elem.content);
        });

        // Edit Mode entry does not automatically steal focus; user explicitly clicks to focus
    }

    formatParenthetical(text) {
        if (!text) return '';
        let trimmed = text.trim();
        if (!trimmed) return '';

        // Strip any existing outer parentheses (including multiples or unmatched)
        while (trimmed.startsWith('(') && trimmed.endsWith(')') && trimmed.length >= 2) {
            trimmed = trimmed.slice(1, -1).trim();
        }
        if (trimmed.startsWith('(')) {
            trimmed = trimmed.slice(1).trim();
        }
        if (trimmed.endsWith(')')) {
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
            prefix.contentEditable = 'false';
            prefix.innerText = (this.currentSceneIdentifier || (this.currentSceneIsSub ? 'Scene 1.A' : 'Scene 1')) + ' :';
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

                const currentIdent = this.currentSceneIdentifier || (this.currentSceneIsSub ? 'Scene 1.A' : 'Scene 1');
                const fullHeading = locVal ? `${currentIdent} : ${built}` : `${currentIdent} : UNTITLED SCENE`;

                const activeSidebarItems = document.querySelectorAll(`.scene-item[data-id="${this.currentSceneId}"] .scene-heading-text`);
                activeSidebarItems.forEach(item => {
                    item.innerText = fullHeading;
                });
                if (this.currentSelectorBadge) {
                    this.currentSelectorBadge.innerText = fullHeading;
                }

                this.markDirty();
                this.calculateLiveStats();
            };

            locationInput.addEventListener('input', syncHeading);
            intextSelect.addEventListener('change', syncHeading);
            timeSelect.addEventListener('change', syncHeading);

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
                    editable.innerText = trans;
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
                this.currentTypeEl.innerText = this.formatTypeLabel(block.dataset.type);
            }
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
                const currentIdent = this.currentSceneIdentifier || (this.currentSceneIsSub ? 'Scene 1.A' : 'Scene 1');
                const fullHeading = cleanHeading ? `${currentIdent} : ${cleanHeading}` : `${currentIdent} : UNTITLED SCENE`;

                const activeSidebarItems = document.querySelectorAll(`.scene-item[data-id="${this.currentSceneId}"] .scene-heading-text`);
                activeSidebarItems.forEach(item => {
                    item.innerText = fullHeading;
                });
                if (this.currentSelectorBadge) {
                    this.currentSelectorBadge.innerText = fullHeading;
                }
            }

            // Character autocomplete trigger
            if (block.dataset.type === 'character') {
                this.handleCharacterInput(editable);
            } else {
                this.hideAutocomplete();
            }
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

            // Enter key screenplay flow logic
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.handleEnterKey(block, editable);
                return;
            }

            // Tab key element type cycling
            if (e.key === 'Tab') {
                e.preventDefault();
                this.cycleElementType(block, e.shiftKey ? -1 : 1);
                return;
            }

            // Backspace on empty block
            if (e.key === 'Backspace' && editable.innerText.trim() === '') {
                const prevBlock = block.previousElementSibling;
                if (prevBlock && prevBlock.classList.contains('script-element-block')) {
                    e.preventDefault();
                    block.remove();
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

            // Arrow Up / Down navigation between blocks
            if (e.key === 'ArrowUp') {
                const sel = window.getSelection();
                if (sel && sel.anchorOffset === 0) {
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
            } else if (e.key === 'ArrowDown') {
                const sel = window.getSelection();
                if (sel && sel.anchorOffset >= editable.innerText.length) {
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
        });
    }

    handleEnterKey(block, editable) {
        const currentType = block.dataset.type;
        const currentText = editable.innerText.trim();

        let nextType = 'action';
        let suggestions = [];

        if (currentType === 'scene_heading') {
            nextType = 'action';
        } else if (currentType === 'action') {
            nextType = 'action';
            suggestions = [{ type: 'character', label: '+ Character' }];
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
        } else if (currentType === 'transition') {
            nextType = 'action';
        } else if (currentType === 'shot') {
            nextType = 'action';
        } else if (currentType === 'note') {
            nextType = 'action';
        }

        const newBlock = this.createElementBlock(nextType, '', block);
        const newEditable = newBlock.querySelector('.element-content:not(.d-none)') || newBlock.querySelector('.element-content');
        if (newEditable) {
            newEditable.focus();
            this.setCursorToStart(newEditable);
        }
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
        } else if (oldType === 'parenthetical' && newType !== 'parenthetical') {
            let trimmed = currentContent.trim();
            if (trimmed.startsWith('(') && trimmed.endsWith(')') && trimmed.length >= 2) {
                currentContent = trimmed.slice(1, -1).trim();
            }
        }

        if (newType === 'scene_heading') {
            const lineWrapper = document.createElement('div');
            lineWrapper.className = 'scene-heading-line';

            const prefix = document.createElement('span');
            prefix.className = 'scene-prefix-label font-screenplay user-select-none';
            prefix.contentEditable = 'false';
            prefix.innerText = (this.currentSceneIdentifier || (this.currentSceneIsSub ? 'Scene 1.A' : 'Scene 1')) + ' :';
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
                    editable.innerText = trans;
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
        this.markDirty();
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
        let sceneHeading = 'INT. LOCATION - DAY';

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

        const targetSceneId = this.currentSceneId;
        const saveVersion = this.changeVersion || 0;
        const payload = this.extractScenePayload();

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

                if ((this.changeVersion || 0) === saveVersion) {
                    this.isDirty = false;
                    this.setSaveStatus('saved', 'Saved ✓');
                } else {
                    this.isDirty = true;
                    this.setSaveStatus('dirty', 'Unsaved changes');
                }

                this.updateStats(result.script_stats);
                this.updateReadModeScene(targetSceneId, payload);
                return result;
            } catch (err) {
                console.error('Save error:', err);
                const isOffline = !navigator.onLine;
                this.setSaveStatus(
                    isOffline ? 'offline' : 'error',
                    isOffline ? 'Offline / connection problem' : 'Save failed (click to retry)'
                );

                clearTimeout(this.saveTimeout);
                this.saveTimeout = setTimeout(() => {
                    if (this.isDirty) {
                        this.saveCurrentScene();
                    }
                }, 4000);

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
            const isActive = Number(sc.id) === Number(this.currentSceneId);
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
                        <li><button type="button" class="dropdown-item btn-action-copy-scene" data-id="${sc.id}"><i class="bi bi-clipboard me-2 text-secondary"></i>Copy Full Scene</button></li>
                        <li><button type="button" class="dropdown-item btn-action-dup" data-id="${sc.id}"><i class="bi bi-copy me-2 text-secondary"></i>Duplicate</button></li>
                        <li><button type="button" class="dropdown-item btn-action-move-up" data-id="${sc.id}"><i class="bi bi-arrow-up me-2"></i>Move Up</button></li>
                        <li><button type="button" class="dropdown-item btn-action-move-down" data-id="${sc.id}"><i class="bi bi-arrow-down me-2"></i>Move Down</button></li>
                        <li><hr class="dropdown-divider"></li>
                        <li><button type="button" class="dropdown-item text-danger btn-action-delete" data-id="${sc.id}" data-badge="${navId}" data-is-sub="${isSub}" data-heading="${escapedHeading}"><i class="bi bi-trash me-2"></i>Delete</button></li>
                    </ul>
                </div>
            `;

            htmlChunks.push(`
                <li class="scene-item ${isSub ? 'sub-scene-item' : ''} ${isActive ? 'active' : ''}" data-id="${sc.id}" data-parent="${sc.parent_scene_id || ''}">
                    <div class="scene-nav-item">
                        <span class="scene-nav-number font-screenplay">${navId}</span>
                        <span class="scene-nav-separator">:</span>
                        <span class="scene-nav-location font-malayalam" title="${cleanLoc.replace(/"/g, '&quot;')}">${cleanLoc}</span>
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

            // Update transition if present
            let transEl = sec.querySelector('.read-element-block.element-type-transition');
            const transitionText = (sc.transition || '').trim();
            if (transitionText) {
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
                document.querySelectorAll('.scene-item').forEach(el => {
                    el.classList.toggle('active', String(el.dataset.id) === String(sceneId));
                });
                if (this.editorMode === 'read') {
                    // In Read Mode: smooth scroll to stable scene anchor without navigation or URL changes
                    this.currentSceneId = Number(sceneId);
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
        if (!this.isSwitchingScene && targetId === Number(this.currentSceneId)) return;

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
        const addedTransition = this.ensurePreviousSceneHasTransition();
        try {
            await this.flushSave();
        } catch (err) {
            console.error('Save failed before appending scene:', err);
            if (addedTransition && addedTransition.parentElement) {
                addedTransition.remove();
                this.calculateLiveStats();
            }
            alert('Could not save the current scene. Scene creation was cancelled to protect your unsaved writing. Please retry once saved.');
            return;
        }

        try {
            this.setSaveStatus('saving', 'Creating scene...');
            const res = await fetch(`/scripts/api/${this.scriptId}/scenes/create/`, {
                method: 'POST',
                headers: this.getHeaders(),
                body: JSON.stringify({
                    heading: 'INT. LOCATION - DAY'
                })
            });
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
                ? 'This will permanently delete this sub-scene. Other scenes will not be affected.'
                : 'This will permanently delete this scene and all of its sub-scenes. This action cannot be undone.';
        }

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
        if (submitBtnText) submitBtnText.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Deleting...';

        try {
            await this.flushSave();
            if (this.currentSceneId && Number(this.currentSceneId) !== Number(sceneId)) {
                const payload = this.extractScenePayload();
                this.updateReadModeScene(this.currentSceneId, payload);
            }
        } catch (err) {
            console.error('Save failed before deleting scene:', err);
            if (submitBtn) submitBtn.disabled = false;
            if (submitBtnText) submitBtnText.innerText = 'Delete Scene';
            alert('Could not save the current scene. Scene deletion was cancelled to protect your unsaved writing. Please retry once saved.');
            return;
        }

        try {
            this.setSaveStatus('saving', 'Deleting scene...');
            const res = await fetch(`/scripts/api/${this.scriptId}/scenes/${sceneId}/delete/`, {
                method: 'POST',
                headers: this.getHeaders(),
            });
            const data = await res.json();
            if (!res.ok || data.status !== 'ok') {
                alert(data.message || 'Cannot delete scene');
                this.setSaveStatus('saved', 'Saved ✓');
                if (submitBtn) submitBtn.disabled = false;
                if (submitBtnText) submitBtnText.innerText = 'Delete Scene';
                return;
            }

            if (this.deleteModalEl) {
                const modal = bootstrap.Modal.getOrCreateInstance(this.deleteModalEl);
                modal.hide();
            }

            this.renderScenesTree(data.scenes_tree);
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
            alert('Failed to delete scene: ' + err.message);
            this.setSaveStatus('error', 'Error deleting scene');
        } finally {
            if (submitBtn) submitBtn.disabled = false;
            if (submitBtnText) submitBtnText.innerText = 'Delete Scene';
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
            const isSearchInput = activeEl && (activeEl.id === 'sceneSearchInput' || activeEl.id === 'offcanvasSceneSearchInput');

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

            if (scrollTarget && this.currentSceneId) {
                const targetSceneEl = document.getElementById(`read-scene-${this.currentSceneId}`);
                if (targetSceneEl) {
                    targetSceneEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
                // Determine which scene is currently closest in view within continuous Read Mode
                const visibleSceneId = this.findVisibleReadModeSceneId();
                if (visibleSceneId && Number(visibleSceneId) !== Number(this.currentSceneId)) {
                    await this.switchScene(visibleSceneId);
                }
                this.setEditorMode('edit');
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
        if (!scenes.length) return this.currentSceneId;
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
        return closestId || this.currentSceneId;
    }

    async handleDoneClick() {
        try {
            this.setSaveStatus('saving', 'Saving before exiting...');
            await this.flushSave();

            // Extract the saved payload to update Read Mode DOM immediately
            const payload = this.extractScenePayload();
            this.updateReadModeScene(this.currentSceneId, payload);

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
                        this.currentSceneId = Number(sceneId);
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
                const currentIdent = (scMeta && scMeta.nav_identifier) || (scMeta && scMeta.scene_identifier) || this.currentSceneIdentifier || (this.currentSceneIsSub ? 'Scene 1.A' : 'Scene 1');
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
                    const contentDiv = document.createElement('div');
                    contentDiv.className = 'element-content font-screenplay font-malayalam';
                    contentDiv.innerText = elem.content || '';
                    block.appendChild(contentDiv);
                    elementsContainer.appendChild(block);
                }
            });
        }

        // 3. Update Transition if present
        let transEl = sceneSection.querySelector('.read-element-block.element-type-transition');
        const transitionText = payload.transition !== undefined ? payload.transition : (this.currentSceneTransition || 'CUT TO:');
        if (transitionText) {
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

    handleCopy(e) {
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

            // If user selected partial text inside a single action/dialogue block, let browser copy plain text inline
            if (selectedBlocks.length === 1) {
                const singleBlock = selectedBlocks[0];
                const ed = singleBlock.querySelector('.element-content:not(.d-none)') || singleBlock.querySelector('.element-content');
                const fullText = (ed ? ed.innerText : '').trim();
                const selText = sel.toString().trim();
                if (selText && selText !== fullText && (singleBlock.dataset.type === 'action' || singleBlock.dataset.type === 'dialogue')) {
                    return;
                }
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

            this.markDirty();
            this.calculateLiveStats();
            return;
        }

        // ----------------------------------------------------
        // BRANCH 2: EXTERNAL CLIPBOARD (PLAIN TEXT ONLY)
        // ----------------------------------------------------
        let externalText = e.clipboardData ? e.clipboardData.getData('text/plain') : '';
        if (!externalText) {
            // Nothing to paste
            return;
        }

        // Intercept external paste - treat purely as plain text
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

        // Insert clean plain text at current caret position
        this.insertPlainTextAtCaret(targetEditable, externalText, isTargetAlreadyFocused);

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
                const hasTransition = elements.some(e => e.type === 'transition');
                if (!hasTransition && transition) {
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
                const hasTransition = elements.some(e => e.type === 'transition');
                if (!hasTransition && transition) {
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
}
