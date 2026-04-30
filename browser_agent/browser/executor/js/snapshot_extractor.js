() => {
    const INTERACTIVE = [
        'a', 'button', 'input', 'textarea', 'select',
        '[role="button"]', '[role="link"]', '[role="tab"]', '[role="menuitem"]',
        '[role="checkbox"]', '[role="radio"]', '[role="option"]',
        '[aria-checked]', '[aria-selected]',
        '[contenteditable="true"]', '[tabindex]'
    ].join(',');

    const CONTAINER_SELECTORS = [
        '[role="row"]', 'tr', 'li', 'article', 'section', 'form',
        '[role="dialog"]', '[role="listitem"]', '[role="gridcell"]', '[role="main"]'
    ].join(',');

    const SNAP_ATTR = 'data-agent-snapshot-id';
    const snapshotId = 's_' + Date.now();

    // Clean previous snapshot attributes
    document.querySelectorAll('[' + SNAP_ATTR + ']').forEach(el => {
        el.removeAttribute(SNAP_ATTR);
    });

    // Visibility check via computed style + bounding rect
    function isVisible(el) {
        const style = window.getComputedStyle(el);
        if (style.display === 'none') return false;
        if (style.visibility === 'hidden') return false;
        if (parseFloat(style.opacity) === 0) return false;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return false;
        return true;
    }

    function isInViewport(rect) {
        return (
            rect.bottom > 0 &&
            rect.right > 0 &&
            rect.top < window.innerHeight &&
            rect.left < window.innerWidth
        );
    }

    // Find nearest semantic container
    function findContainer(el) {
        let current = el.parentElement;
        while (current && current !== document.body) {
            if (current.matches(CONTAINER_SELECTORS)) {
                return current;
            }
            current = current.parentElement;
        }
        return null;
    }

    function getCleanText(el, maxLen) {
        const text = (el.innerText || el.textContent || '').trim();
        return text.length > maxLen ? text.slice(0, maxLen) + '...' : text;
    }

    function getLabel(el) {
        // aria-label first
        const ariaLabel = el.getAttribute('aria-label');
        if (ariaLabel) return ariaLabel;

        // associated <label>
        const id = el.id;
        if (id) {
            const label = document.querySelector('label[for="' + id + '"]');
            if (label) return label.textContent.trim();
        }

        // parent label
        const parentLabel = el.closest('label');
        if (parentLabel) {
            return parentLabel.textContent.trim().slice(0, 100);
        }

        // aria-labelledby
        const labelledBy = el.getAttribute('aria-labelledby');
        if (labelledBy) {
            const labelEl = document.getElementById(labelledBy);
            if (labelEl) return labelEl.textContent.trim();
        }

        return null;
    }

    function isCheckboxLike(el) {
        const role = el.getAttribute('role');
        const type = el.getAttribute('type');
        return (
            type === 'checkbox' ||
            role === 'checkbox' ||
            role === 'menuitemcheckbox' ||
            el.hasAttribute('aria-checked')
        );
    }

    function getFingerprint(el) {
        const parts = [
            el.tagName,
            el.getAttribute('role') || '',
            el.getAttribute('type') || '',
            el.getAttribute('name') || '',
            (getLabel(el) || '').slice(0, 50)
        ];
        return parts.join(':');
    }

    // Collect containers for state tracking
    const containerMap = new Map(); // DOM element -> container info
    let containerIdx = 0;

    // Process interactive elements
    const allInteractive = document.querySelectorAll(INTERACTIVE);
    const elements = [];
    let elementIdx = 0;

    for (const el of allInteractive) {
        const visible = isVisible(el);
        const rect = el.getBoundingClientRect();
        const inViewport = visible && isInViewport(rect);

        const tag = el.tagName;
        const role = el.getAttribute('role') || null;
        const type = el.getAttribute('type') || null;
        const text = getCleanText(el, 200);
        const label = getLabel(el);
        const name = el.getAttribute('name') || null;
        const placeholder = el.getAttribute('placeholder') || null;
        const value = el.value !== undefined ? el.value : null;
        const href = el.getAttribute('href') || null;
        const enabled = !el.disabled && !el.getAttribute('aria-disabled');

        // Checked/selected state
        let checked = null;
        let selected = null;
        if ('checked' in el) checked = el.checked;
        if ('selected' in el) selected = el.selected;
        const ariaChecked = el.getAttribute('aria-checked');
        const ariaSelected = el.getAttribute('aria-selected');

        // Container context
        const container = findContainer(el);
        let containerId = null;
        let containerRole = null;
        let rowIndex = null;
        let context = null;

        if (container) {
            if (!containerMap.has(container)) {
                const cId = 'c' + containerIdx++;
                const cRole = container.getAttribute('role') || container.tagName.toLowerCase();
                containerMap.set(container, { id: cId, role: cRole, element: container });
            }
            const cInfo = containerMap.get(container);
            containerId = cInfo.id;
            containerRole = cInfo.role;
            context = getCleanText(container, 500);

            // Row index: position among siblings of same type
            if (container.parentElement) {
                const siblings = [...container.parentElement.children].filter(
                    c => c.tagName === container.tagName
                );
                rowIndex = siblings.indexOf(container);
                if (rowIndex === -1) rowIndex = null;
            }
        }

        const elementId = 'e' + elementIdx++;
        el.setAttribute(SNAP_ATTR, elementId);

        let isSelectionControl = false;
        let selectionScope = null;
        if (isCheckboxLike(el)) {
            if (containerId !== null && rowIndex !== null) {
                isSelectionControl = true;
                selectionScope = 'item';
            } else if (containerId === null && rowIndex === null) {
                isSelectionControl = true;
                selectionScope = 'global';
            }
        }

        elements.push({
            id: elementId,
            tag: tag,
            role: role,
            type: type,
            text: text,
            label: label,
            name: name,
            placeholder: placeholder,
            value: (value !== null && value !== undefined) ? String(value).slice(0, 200) : null,
            href: href,
            visible: visible,
            enabled: enabled,
            checked: checked,
            selected: selected,
            aria_checked: ariaChecked,
            aria_selected: ariaSelected,
            in_viewport: inViewport,
            rect: { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) },
            context: context,
            row_index: rowIndex,
            container_id: containerId,
            container_role: containerRole,
            fingerprint: getFingerprint(el),
            is_selection_control: isSelectionControl,
            selection_scope: selectionScope
        });
    }

    // Build container states
    const containers = [];
    for (const [domEl, cInfo] of containerMap) {
        // Count checked/selected items within this container
        const interactiveInContainer = domEl.querySelectorAll(INTERACTIVE);
        let selectedCount = 0;
        let checkedCount = 0;
        let totalItems = 0;

        for (const child of interactiveInContainer) {
            const isCheckable = (
                child.getAttribute('type') === 'checkbox' ||
                child.getAttribute('role') === 'checkbox' ||
                child.getAttribute('role') === 'option' ||
                child.hasAttribute('aria-checked') ||
                child.hasAttribute('aria-selected')
            );
            if (!isCheckable) continue;
            totalItems++;

            if (child.checked === true || child.getAttribute('aria-checked') === 'true') {
                checkedCount++;
            }
            if (child.selected === true || child.getAttribute('aria-selected') === 'true') {
                selectedCount++;
            }
        }

        // Only include containers that have checkable items
        if (totalItems > 0) {
            containers.push({
                id: cInfo.id,
                role: cInfo.role,
                selector_hint: domEl.tagName.toLowerCase() + (domEl.id ? '#' + domEl.id : '') + (domEl.className ? '.' + String(domEl.className).split(' ')[0] : ''),
                selected_count: selectedCount,
                checked_count: checkedCount,
                total_items: totalItems
            });
        }
    }

    // Dialogs
    const dialogs = [];
    for (const d of document.querySelectorAll('dialog, [role="dialog"], [role="alertdialog"]')) {
        if (isVisible(d)) {
            dialogs.push({
                type: d.getAttribute('role') || 'dialog',
                text: getCleanText(d, 300)
            });
        }
    }

    // Toasts / notifications
    const toasts = [];
    for (const t of document.querySelectorAll('[role="alert"], [role="status"], .toast, .notification, .snackbar')) {
        if (isVisible(t)) {
            toasts.push({
                text: getCleanText(t, 200),
                visible: true
            });
        }
    }

    // Text blocks from main content areas
    const textBlocks = [];
    const mainAreas = document.querySelectorAll('main, [role="main"], article, .content');
    if (mainAreas.length > 0) {
        for (const area of mainAreas) {
            const text = getCleanText(area, 1000);
            if (text) {
                const location = area.getAttribute('role') || area.tagName.toLowerCase();
                textBlocks.push({ location: location, text: text });
            }
        }
    } else {
        // Fallback: body text excerpt
        const bodyText = getCleanText(document.body, 1000);
        if (bodyText) {
            textBlocks.push({ location: 'body', text: bodyText });
        }
    }

    // Focused element
    let focusedElement = null;
    if (document.activeElement && document.activeElement !== document.body) {
        const focusedId = document.activeElement.getAttribute(SNAP_ATTR);
        if (focusedId) focusedElement = focusedId;
    }

    return {
        snapshot_id: snapshotId,
        url: window.location.href,
        title: document.title,
        viewport: { width: window.innerWidth, height: window.innerHeight },
        elements: elements,
        state: {
            containers: containers,
            dialogs: dialogs,
            toasts: toasts,
            text_blocks: textBlocks,
            focused_element: focusedElement
        }
    };
}