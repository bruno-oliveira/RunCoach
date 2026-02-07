/**
 * Modal Utility Functions
 * 
 * Provides utilities for managing modals/dialogs including:
 * - Opening and closing modals
 * - Escape key handling
 * - Click-outside-to-close
 * - Focus trap for accessibility
 * - Multiple modal support
 */

const ModalManager = {
  openModals: new Set(),
  focusableSelectors: 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
  
  /**
   * Opens a modal by ID
   * @param {string} modalId - The ID of the modal element
   */
  openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) {
      console.error(`Modal with ID "${modalId}" not found`);
      return;
    }
    
    modal.classList.add('is-open');
    if (modal.style) modal.style.display = 'flex';
    this.openModals.add(modalId);
    
    // Store the element that had focus before opening
    modal.dataset.previousFocus = document.activeElement?.id || '';
    
    // Prevent body scroll
    if (this.openModals.size === 1 && document.body.style) {
      document.body.style.overflow = 'hidden';
    }
    
    // Set focus to first focusable element
    this._trapFocus(modal);
    
    // Trigger custom event
    modal.dispatchEvent(new CustomEvent('modal:open', { bubbles: true }));
  },
  
  /**
   * Closes a modal by ID
   * @param {string} modalId - The ID of the modal element
   */
  closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) {
      console.error(`Modal with ID "${modalId}" not found`);
      return;
    }
    
    modal.classList.remove('is-open');
    if (modal.style) modal.style.display = 'none';
    this.openModals.delete(modalId);
    
    // Restore body scroll if no modals are open
    if (this.openModals.size === 0 && document.body.style) {
      document.body.style.overflow = '';
    }
    
    // Restore focus to previous element
    const previousFocusId = modal.dataset.previousFocus;
    if (previousFocusId) {
      const previousElement = document.getElementById(previousFocusId);
      previousElement?.focus();
    }
    
    // Trigger custom event
    modal.dispatchEvent(new CustomEvent('modal:close', { bubbles: true }));
  },
  
  /**
   * Closes all open modals
   */
  closeAllModals() {
    const modalsToClose = Array.from(this.openModals);
    modalsToClose.forEach(modalId => this.closeModal(modalId));
  },
  
  /**
   * Toggles a modal's open state
   * @param {string} modalId - The ID of the modal element
   */
  toggleModal(modalId) {
    if (this.openModals.has(modalId)) {
      this.closeModal(modalId);
    } else {
      this.openModal(modalId);
    }
  },
  
  /**
   * Checks if a modal is currently open
   * @param {string} modalId - The ID of the modal element
   * @returns {boolean}
   */
  isModalOpen(modalId) {
    return this.openModals.has(modalId);
  },
  
  /**
   * Sets up focus trap for accessibility
   * @private
   * @param {HTMLElement} modal - The modal element
   */
  _trapFocus(modal) {
    const focusableElements = modal.querySelectorAll(this.focusableSelectors);
    const firstFocusable = focusableElements[0];
    const lastFocusable = focusableElements[focusableElements.length - 1];
    
    // Focus first element
    firstFocusable?.focus();
    
    // Handle tab key navigation
    const handleTabKey = (e) => {
      if (e.key !== 'Tab') return;
      
      if (e.shiftKey) {
        // Shift + Tab
        if (document.activeElement === firstFocusable) {
          e.preventDefault();
          lastFocusable?.focus();
        }
      } else {
        // Tab
        if (document.activeElement === lastFocusable) {
          e.preventDefault();
          firstFocusable?.focus();
        }
      }
    };
    
    // Store handler reference for cleanup
    modal._tabHandler = handleTabKey;
    modal.addEventListener('keydown', handleTabKey);
  },
  
  /**
   * Initializes modal event listeners
   */
  init() {
    // Escape key handler
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.openModals.size > 0) {
        const lastModal = Array.from(this.openModals).pop();
        this.closeModal(lastModal);
      }
    });
    
    // Click outside to close handler
    document.addEventListener('click', (e) => {
      if (this.openModals.size === 0) return;
      
      // Check if click is on backdrop
      if (e.target.classList.contains('modal') || e.target.classList.contains('modal-backdrop')) {
        const modalId = e.target.id || e.target.closest('.modal')?.id;
        if (modalId && this.openModals.has(modalId)) {
          this.closeModal(modalId);
        }
      }
    });
    
    // Close button handler (delegate)
    document.addEventListener('click', (e) => {
      const closeBtn = e.target.closest('.modal-close, [data-modal-close]');
      if (closeBtn) {
        const modal = closeBtn.closest('.modal');
        if (modal && this.openModals.has(modal.id)) {
          this.closeModal(modal.id);
        }
      }
    });
    
    // Open button handler (delegate)
    document.addEventListener('click', (e) => {
      const openBtn = e.target.closest('[data-modal-open]');
      if (openBtn) {
        const modalId = openBtn.dataset.modalOpen;
        if (modalId) {
          this.openModal(modalId);
        }
      }
    });
    
    // Toggle button handler (delegate)
    document.addEventListener('click', (e) => {
      const toggleBtn = e.target.closest('[data-modal-toggle]');
      if (toggleBtn) {
        const modalId = toggleBtn.dataset.modalToggle;
        if (modalId) {
          this.toggleModal(modalId);
        }
      }
    });
  }
};

// Global window functions for backwards compatibility
window.openModal = (modalId) => ModalManager.openModal(modalId);
window.closeModal = (modalId) => ModalManager.closeModal(modalId);
window.closeAllModals = () => ModalManager.closeAllModals();
window.toggleModal = (modalId) => ModalManager.toggleModal(modalId);

// Initialize on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => ModalManager.init());
} else {
  ModalManager.init();
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ModalManager;
}
