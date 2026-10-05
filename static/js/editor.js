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
        this.activeElementBlock = null;
        this.scenesTree = [];
        this.currentSceneIsSub = false;

        // Autocomplete
        this.autocompleteDropdown = document.getElementById('characterAutocomplete');
        this.autocompleteIndex = -1;

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
        try {
            this.setSaveStatus('saving', 'Loading scene...');
            const res = await fetch(`/scripts/api/${this.scriptId}/scenes/${this.currentSceneId}/`);
            if (!res.ok) throw new Error(`Failed to load scene (HTTP ${res.status})`);
            const data = await res.json();
            
            this.characters = data.characters || this.characters;
            this.scenesTree = data.scenes_tree || [];
            this.currentSceneIsSub = Boolean(data.scene.is_sub_scene);
            this.currentMainSceneId = data.scene.parent_scene_id || data.scene.id;
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
            this.renderScenesTree(this.scenesTree);
            this.updateSceneContextControls(data.scene);
            this.updateStats(data.script_stats);
            this.setSaveStatus('saved', 'Saved ✓');
            this.isDirty = false;
            this.needsQueuedSave = false;
        } catch (err) {
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
        this.currentSceneTransition = (scene.transition || this.currentSceneTransition || 'CUT TO').trim();

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

        // Render Scene-End Transition Bar before notes
        this.renderSceneEndTransition();

        // Render any Notes
        noteElements.forEach(elem => {
            this.createElementBlock(elem.element_type, elem.content);
        });

        // Focus location input or first editable block
        const locInput = this.pageContainer.querySelector('.heading-location-input');
        if (locInput) {
            locInput.focus();
        } else {
            const firstBlock = this.pageContainer.querySelector('.element-content:not(.d-none)');
            if (firstBlock) {
                firstBlock.focus();
            }
        }
    }

    renderSceneEndTransition() {
        const transBar = document.createElement('div');
        transBar.className = 'scene-end-transition-bar user-select-none';
        transBar.contentEditable = 'false';

        const standardTransitions = ['CUT TO', 'DISSOLVE TO', 'FADE OUT', 'INTERCUT', 'CUT BACK TO'];
        const currentTrans = (this.currentSceneTransition || 'CUT TO').trim();
        const isStandard = standardTransitions.includes(currentTrans);

        // Clean clickable display element (visible by default)
        const displayEl = document.createElement('div');
        displayEl.className = 'scene-end-transition-display font-screenplay';
        displayEl.title = 'Click to change scene-end transition';
        displayEl.innerText = currentTrans || 'CUT TO';

        // In-place dropdown / picker (hidden by default)
        const pickerEl = document.createElement('div');
        pickerEl.className = 'scene-end-transition-picker';
        pickerEl.style.display = 'none';

        const select = document.createElement('select');
        select.className = 'form-select form-select-sm scene-end-transition-select font-screenplay';
        select.title = 'Select Scene-End Transition';

        select.innerHTML = `
            <option value="CUT TO" ${currentTrans === 'CUT TO' ? 'selected' : ''}>CUT TO</option>
            <option value="DISSOLVE TO" ${currentTrans === 'DISSOLVE TO' ? 'selected' : ''}>DISSOLVE TO</option>
            <option value="FADE OUT" ${currentTrans === 'FADE OUT' ? 'selected' : ''}>FADE OUT</option>
            <option value="INTERCUT" ${currentTrans === 'INTERCUT' ? 'selected' : ''}>INTERCUT</option>
            <option value="CUT BACK TO" ${currentTrans === 'CUT BACK TO' ? 'selected' : ''}>CUT BACK TO</option>
            <option value="Other" ${!isStandard ? 'selected' : ''}>Other</option>
        `;

        const customInput = document.createElement('input');
        customInput.type = 'text';
        customInput.className = 'form-control form-control-sm scene-end-transition-custom font-screenplay font-malayalam';
        customInput.placeholder = 'Enter custom transition...';
        customInput.spellcheck = false;
        customInput.autocomplete = 'off';
        customInput.value = !isStandard ? currentTrans : '';
        customInput.style.display = !isStandard ? 'block' : 'none';

        const closePicker = () => {
            pickerEl.style.display = 'none';
            displayEl.style.display = 'inline-block';
            displayEl.innerText = this.currentSceneTransition || 'CUT TO';
        };

        const openPicker = () => {
            displayEl.style.display = 'none';
            pickerEl.style.display = 'inline-flex';
            if (standardTransitions.includes(this.currentSceneTransition)) {
                select.value = this.currentSceneTransition;
                customInput.style.display = 'none';
                customInput.value = '';
            } else {
                select.value = 'Other';
                customInput.style.display = 'block';
                customInput.value = this.currentSceneTransition;
            }
            select.focus();
        };

        displayEl.addEventListener('click', (e) => {
            e.stopPropagation();
            openPicker();
        });

        select.addEventListener('change', (e) => {
            e.stopPropagation();
            if (select.value === 'Other') {
                customInput.style.display = 'block';
                customInput.focus();
                customInput.select();
                const customVal = customInput.value.trim();
                this.currentSceneTransition = customVal || 'Other';
            } else {
                customInput.style.display = 'none';
                this.currentSceneTransition = select.value;
                closePicker();
            }
            this.markDirty();
        });

        customInput.addEventListener('input', (e) => {
            const val = customInput.value.trim();
            this.currentSceneTransition = val || 'Other';
            this.markDirty();
        });

        customInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                closePicker();
            } else if (e.key === 'Escape') {
                e.preventDefault();
                closePicker();
            }
        });

        const handleOutsideClick = (e) => {
            if (!transBar.contains(e.target) && pickerEl.style.display !== 'none') {
                closePicker();
            }
        };
        document.addEventListener('click', handleOutsideClick);

        pickerEl.appendChild(select);
        pickerEl.appendChild(customInput);
        transBar.appendChild(displayEl);
        transBar.appendChild(pickerEl);
        this.pageContainer.appendChild(transBar);
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

        if (insertAfter && insertAfter.parentNode === this.pageContainer) {
            this.pageContainer.insertBefore(block, insertAfter.nextSibling);
        } else if (type === 'note') {
            this.pageContainer.appendChild(block);
        } else {
            const transBar = this.pageContainer.querySelector('.scene-end-transition-bar');
            if (transBar && transBar.parentNode === this.pageContainer) {
                this.pageContainer.insertBefore(block, transBar);
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

        // Input & Changes
        editable.addEventListener('input', () => {
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
                    const prevEditable = prevBlock.querySelector('.element-content');
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
                        const prevEditable = prevBlock.querySelector('.element-content');
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
                        const nextEditable = nextBlock.querySelector('.element-content');
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

        if (currentType === 'scene_heading') {
            nextType = 'action';
        } else if (currentType === 'action') {
            nextType = currentText ? 'action' : 'character';
        } else if (currentType === 'character') {
            nextType = 'dialogue';
        } else if (currentType === 'parenthetical') {
            nextType = 'dialogue';
        } else if (currentType === 'dialogue') {
            nextType = currentText ? 'character' : 'action';
        } else if (currentType === 'transition') {
            nextType = 'scene_heading';
        } else if (currentType === 'shot') {
            nextType = 'action';
        } else if (currentType === 'note') {
            nextType = 'action';
        }

        const newBlock = this.createElementBlock(nextType, '', block);
        const newEditable = newBlock.querySelector('.element-content');
        newEditable.focus();
        this.markDirty();
        this.calculateLiveStats();
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
        block.dataset.type = newType;
        const tag = block.querySelector('.element-type-tag');
        if (tag) tag.innerText = this.formatTypeLabel(newType);

        let editable = block.querySelector('.element-content');

        if (oldType !== 'scene_heading' && newType === 'scene_heading') {
            const currentContent = editable ? editable.innerText : '';
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
            const currentContent = editable ? editable.innerText : '';
            if (lineWrapper) {
                lineWrapper.remove();
            }
            editable = document.createElement('div');
            editable.className = 'element-content font-screenplay font-malayalam';
            editable.contentEditable = 'true';
            editable.spellcheck = false;
            editable.dataset.placeholder = this.getPlaceholderForType(newType);
            editable.innerText = currentContent;
            block.appendChild(editable);
            this.bindElementEvents(block, editable);
        } else if (editable) {
            editable.dataset.placeholder = this.getPlaceholderForType(newType);
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

        // Position dropdown near the element
        const rect = editable.getBoundingClientRect();
        this.autocompleteDropdown.style.left = `${rect.left}px`;
        this.autocompleteDropdown.style.top = `${rect.bottom + window.scrollY + 4}px`;
        this.autocompleteDropdown.style.display = 'block';
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
        this.autocompleteIndex = -1;
    }

    // ----------------------------------------------------
    // ROBUST AUTO-SAVE & PERSISTENCE (Task 7 Architecture)
    // ----------------------------------------------------
    markDirty() {
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
                content = contentEl ? contentEl.innerText : '';
            }

            elementsData.push({
                element_type: type,
                content: content,
                order: index,
            });
        });

        return {
            heading: sceneHeading,
            transition: this.currentSceneTransition || 'CUT TO',
            elements: elementsData,
        };
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

        if (this.isSaving) {
            this.needsQueuedSave = true;
            return this.activeSavePromise || Promise.resolve();
        }

        clearTimeout(this.saveTimeout);
        this.isSaving = true;
        this.needsQueuedSave = false;
        this.setSaveStatus('saving', 'Saving...');

        const targetSceneId = this.currentSceneId;
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

                this.isSaving = false;

                if (this.needsQueuedSave) {
                    this.needsQueuedSave = false;
                    return this.saveCurrentScene(true);
                }

                this.isDirty = false;
                this.setSaveStatus('saved', 'Saved ✓');
                this.updateStats(result.script_stats);
                return result;
            } catch (err) {
                console.error('Save error:', err);
                this.isSaving = false;
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
                this.activeSavePromise = null;
            }
        })();

        return this.activeSavePromise;
    }

    async flushSave() {
        clearTimeout(this.saveTimeout);
        if (this.isSaving && this.activeSavePromise) {
            await this.activeSavePromise.catch(() => {});
        }
        if (this.isDirty) {
            await this.saveCurrentScene(true);
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

        let totalSceneCount = 0;
        const htmlChunks = [];

        tree.forEach((mainSc, mainIdx) => {
            totalSceneCount++;
            const isMainActive = Number(mainSc.id) === Number(this.currentSceneId);
            const isFirstMain = mainIdx === 0;
            const isLastMain = mainIdx === tree.length - 1;

            const safeHeading = (mainSc.clean_heading || mainSc.heading || '').replace(/"/g, '&quot;');
            const fullMainHeading = mainSc.full_display_heading || `${mainSc.scene_identifier || mainSc.display_number_formatted} : ${mainSc.clean_heading || mainSc.heading}`;
            htmlChunks.push(`
                <li class="scene-item ${isMainActive ? 'active' : ''}" data-id="${mainSc.id}">
                    <div class="d-flex align-items-center flex-grow-1 overflow-hidden">
                        <span class="scene-heading-text font-screenplay">${fullMainHeading}</span>
                    </div>
                    <div class="scene-item-actions dropdown">
                        <button class="btn btn-sm btn-link text-muted p-0 border-0 dropdown-toggle" type="button" data-bs-toggle="dropdown" data-bs-popper-config='{"strategy":"fixed"}' aria-expanded="false">
                            <i class="bi bi-three-dots-vertical"></i>
                        </button>
                        <ul class="dropdown-menu dropdown-menu-end shadow-sm small">
                            <li><button type="button" class="dropdown-item btn-action-insert-before" data-id="${mainSc.id}" data-is-sub="false" data-heading="${safeHeading}"><i class="bi bi-arrow-up-circle me-2 text-primary"></i>Insert Scene Before</button></li>
                            <li><button type="button" class="dropdown-item btn-action-insert-after" data-id="${mainSc.id}" data-is-sub="false" data-heading="${safeHeading}"><i class="bi bi-arrow-down-circle me-2 text-success"></i>Insert Scene After</button></li>
                            <li><button type="button" class="dropdown-item btn-action-add-sub" data-id="${mainSc.id}" data-heading="${safeHeading}"><i class="bi bi-diagram-3 me-2 text-info"></i>Add Sub Scene</button></li>
                            <li><hr class="dropdown-divider"></li>
                            <li><button type="button" class="dropdown-item btn-action-move-up ${isFirstMain ? 'disabled' : ''}" data-id="${mainSc.id}"><i class="bi bi-arrow-up me-2"></i>Move Up</button></li>
                            <li><button type="button" class="dropdown-item btn-action-move-down ${isLastMain ? 'disabled' : ''}" data-id="${mainSc.id}"><i class="bi bi-arrow-down me-2"></i>Move Down</button></li>
                            <li><button type="button" class="dropdown-item btn-action-dup" data-id="${mainSc.id}"><i class="bi bi-copy me-2"></i>Duplicate</button></li>
                            <li><hr class="dropdown-divider"></li>
                            <li><button type="button" class="dropdown-item text-danger btn-action-delete" data-id="${mainSc.id}" data-badge="${mainSc.display_number}" data-is-sub="false" data-heading="${safeHeading}"><i class="bi bi-trash me-2"></i>Delete</button></li>
                        </ul>
                    </div>
                </li>
            `);

            // Sub scenes
            if (mainSc.sub_scenes && mainSc.sub_scenes.length > 0) {
                mainSc.sub_scenes.forEach((subSc, subIdx) => {
                    totalSceneCount++;
                    const isSubActive = Number(subSc.id) === Number(this.currentSceneId);
                    const isFirstSub = subIdx === 0;
                    const isLastSub = subIdx === mainSc.sub_scenes.length - 1;
                    const safeSubHeading = (subSc.clean_heading || subSc.heading || '').replace(/"/g, '&quot;');
                    const fullSubHeading = subSc.full_display_heading || `${subSc.scene_identifier || subSc.display_number_formatted} : ${subSc.clean_heading || subSc.heading}`;

                    htmlChunks.push(`
                        <li class="scene-item sub-scene-item ps-4 ${isSubActive ? 'active' : ''}" data-id="${subSc.id}" data-parent="${mainSc.id}">
                            <div class="d-flex align-items-center flex-grow-1 overflow-hidden">
                                <span class="sub-scene-indicator text-muted me-1">↳</span>
                                <span class="scene-heading-text font-screenplay">${fullSubHeading}</span>
                            </div>
                            <div class="scene-item-actions dropdown">
                                <button class="btn btn-sm btn-link text-muted p-0 border-0 dropdown-toggle" type="button" data-bs-toggle="dropdown" data-bs-popper-config='{"strategy":"fixed"}' aria-expanded="false">
                                    <i class="bi bi-three-dots-vertical"></i>
                                </button>
                                <ul class="dropdown-menu dropdown-menu-end shadow-sm small">
                                    <li><button type="button" class="dropdown-item btn-action-insert-before" data-id="${subSc.id}" data-is-sub="true" data-heading="${safeSubHeading}"><i class="bi bi-arrow-up-circle me-2 text-primary"></i>Insert Sub Scene Before</button></li>
                                    <li><button type="button" class="dropdown-item btn-action-insert-after" data-id="${subSc.id}" data-is-sub="true" data-heading="${safeSubHeading}"><i class="bi bi-arrow-down-circle me-2 text-success"></i>Insert Sub Scene After</button></li>
                                    <li><hr class="dropdown-divider"></li>
                                    <li><button type="button" class="dropdown-item btn-action-move-up ${isFirstSub ? 'disabled' : ''}" data-id="${subSc.id}"><i class="bi bi-arrow-up me-2"></i>Move Up</button></li>
                                    <li><button type="button" class="dropdown-item btn-action-move-down ${isLastSub ? 'disabled' : ''}" data-id="${subSc.id}"><i class="bi bi-arrow-down me-2"></i>Move Down</button></li>
                                    <li><button type="button" class="dropdown-item btn-action-dup" data-id="${subSc.id}"><i class="bi bi-copy me-2"></i>Duplicate</button></li>
                                    <li><hr class="dropdown-divider"></li>
                                    <li><button type="button" class="dropdown-item text-danger btn-action-delete" data-id="${subSc.id}" data-badge="${subSc.display_number}" data-is-sub="true" data-heading="${safeSubHeading}"><i class="bi bi-trash me-2"></i>Delete</button></li>
                                </ul>
                            </div>
                        </li>
                    `);
                });
            }
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

        if (this.sidebarSceneCountEl) this.sidebarSceneCountEl.innerText = totalSceneCount;
        if (this.offcanvasSceneCountEl) this.offcanvasSceneCountEl.innerText = totalSceneCount;
        if (this.sceneCountEl) this.sceneCountEl.innerText = `${totalSceneCount} scenes`;
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

            // 6. Duplicate
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
                await this.switchScene(sceneId);
                if (this.bsOffcanvas && this.offcanvasEl && this.offcanvasEl.classList.contains('show')) {
                    this.bsOffcanvas.hide();
                }
            }
        });
    }

    async switchScene(newSceneId) {
        const targetId = Number(newSceneId);
        if (targetId === Number(this.currentSceneId)) return;

        try {
            await this.flushSave();
        } catch (err) {
            const proceed = confirm('Could not save current scene due to a network error. Switch anyway? (Unsaved changes will remain in browser memory)');
            if (!proceed) return;
        }

        document.querySelectorAll('.scene-item').forEach(item => {
            item.classList.toggle('active', Number(item.dataset.id) === targetId);
        });

        this.currentSceneId = targetId;
        window.history.replaceState(null, '', `?scene=${targetId}`);
        await this.loadCurrentScene();
    }

    // ----------------------------------------------------
    // SCENE CREATION, INSERTION, SUB-SCENE & MOVE OPERATIONS
    // ----------------------------------------------------
    async appendScene() {
        try {
            await this.flushSave();
        } catch (err) {
            console.warn('Flush save warning before appending scene:', err);
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
            console.warn('Flush save warning before creating sub-scene:', err);
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
        try {
            await this.flushSave();
        } catch (err) {
            console.warn('Flush save warning before inserting scene:', err);
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
            console.warn('Flush save warning before creating sub-scene:', err);
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
        } catch (err) {
            console.warn('Flush save warning before moving scene:', err);
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
                await this.loadCurrentScene();
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
            console.warn('Flush save warning before duplicating scene:', err);
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
        } catch (err) {
            console.warn('Flush save warning before deleting scene:', err);
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
                await this.switchScene(data.fallback_scene_id);
            } else {
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
    getPreviousScenes() {
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
            // Find parent if it is a sub-scene or use main scene
            const target = sc.is_sub_scene && sc.parent_scene_id
                ? (previousItems.find(p => Number(p.id) === Number(sc.parent_scene_id)) || sc)
                : sc;
            if (target && !seen.has(Number(target.id))) {
                seen.add(Number(target.id));
                eligible.push(target);
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

        const scenes = this.getPreviousScenes();
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
            const fullHeading = sc.full_display_heading || `${sc.scene_identifier || sc.display_number_formatted} : ${sc.clean_heading || sc.heading}`;
            return `
                <button type="button" class="list-group-item list-group-item-action d-flex align-items-center justify-content-between py-2 px-3 border-0 border-bottom editor-scene-select-item" data-scene-id="${sc.id}">
                    <span class="font-screenplay font-malayalam fw-semibold text-dark text-wrap me-2" style="word-break: break-word; text-align: left;">${fullHeading}</span>
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
                const scenes = this.getPreviousScenes();
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
            console.warn('Flush save warning before creating scene selection:', err);
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
        if (this.sceneCountEl) this.sceneCountEl.innerText = `${stats.scene_count} scenes`;
        if (this.sidebarSceneCountEl) this.sidebarSceneCountEl.innerText = stats.scene_count;
        if (this.offcanvasSceneCountEl) this.offcanvasSceneCountEl.innerText = stats.scene_count;
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
}
