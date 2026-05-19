/**
 * API Client Utility
 * 
 * Unified HTTP client for all API requests with:
 * - Automatic error handling
 * - Auto-retry logic
 * - Token authentication
 * - Toast notifications
 * - Request/response interceptors
 */

const ApiClient = {
  BASE_URL: window.location.origin,
  MAX_RETRIES: 3,
  RETRY_DELAY: 1000,
  TIMEOUT: 30000,
  
  /**
   * Builds headers for requests
   * @private
   * @param {Object} customHeaders - Additional headers
   * @returns {Object}
   */
  _buildHeaders(customHeaders = {}) {
    return {
      'Content-Type': 'application/json',
      ...customHeaders
    };
  },
  
  /**
   * Shows a toast notification
   * @private
   * @param {string} message - The message to display
   * @param {string} type - success, error, warning, info
   */
  _showToast(message, type = 'info') {
    // Check if toast container exists, create if not
    let container = document.querySelector('.toast-container');
    if (!container) {
      container = document.createElement('div');
      container.className = 'toast-container';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const icons = {
      success: '\u2713',
      error: '\u2715',
      warning: '\u0021',
      info: 'i'
    };

    // Sanitize and format message
    const safeMessage = message
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\n/g, '<br>');

    toast.innerHTML = `
      <span class="toast-icon">${icons[type] || icons.info}</span>
      <div class="toast-content">
        <div class="toast-message">${safeMessage}</div>
      </div>
      <button class="toast-close" aria-label="Close">\u2715</button>
      <div class="toast-progress"></div>
    `;

    container.appendChild(toast);

    const dismiss = () => {
      if (toast.parentNode) {
        toast.classList.add('toast-exit');
        setTimeout(() => toast.remove(), 300);
      }
    };

    // Auto-remove after 8 seconds
    const autoTimer = setTimeout(dismiss, 8000);

    // Manual close
    toast.querySelector('.toast-close').addEventListener('click', () => {
      clearTimeout(autoTimer);
      dismiss();
    });
  },
  
  /**
   * Handles API errors
   * @private
   * @param {Response} response - Fetch response object
   * @throws {Error}
   */
  async _handleError(response) {
    let errorMessage = `Request failed: ${response.status} ${response.statusText}`;
    
    try {
      const data = await response.json();
      errorMessage = data.detail || data.message || errorMessage;
    } catch {
      // Response is not JSON, use default message
    }
    
    // Handle specific status codes
    if (response.status === 401) {
      errorMessage = 'Authentication required. Please log in.';
      // Optionally redirect to login
      // window.location.href = '/login';
    } else if (response.status === 403) {
      errorMessage = 'Access denied. You do not have permission.';
    } else if (response.status === 404) {
      errorMessage = 'Resource not found.';
    } else if (response.status >= 500) {
      errorMessage = 'Server error. Please try again later.';
    }
    
    this._showToast(errorMessage, 'error');
    throw new Error(errorMessage);
  },
  
  /**
   * Delays execution for retry logic
   * @private
   * @param {number} ms - Milliseconds to delay
   */
  _delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  },
  
  /**
   * Makes an HTTP request with retry logic
   * @private
   * @param {string} url - Request URL
   * @param {Object} options - Fetch options
   * @param {number} retryCount - Current retry attempt
   * @returns {Promise<Response>}
   */
  async _fetchWithRetry(url, options, retryCount = 0) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), this.TIMEOUT);
      
      const response = await fetch(url, {
        ...options,
        credentials: 'same-origin',
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (!response.ok) {
        await this._handleError(response);
      }
      
      return response;
    } catch (error) {
      // Retry on network errors or timeouts
      if (retryCount < this.MAX_RETRIES && 
          (error.name === 'AbortError' || error.message.includes('fetch'))) {
        const delay = this.RETRY_DELAY * Math.pow(2, retryCount);
        await this._delay(delay);
        return this._fetchWithRetry(url, options, retryCount + 1);
      }
      
      throw error;
    }
  },
  
  /**
   * Makes a GET request
   * @param {string} url - Request URL (relative or absolute)
   * @param {Object} options - Additional fetch options
   * @returns {Promise<any>}
   */
  async get(url, options = {}) {
    const fullUrl = url.startsWith('http') ? url : `${this.BASE_URL}${url}`;
    
    const response = await this._fetchWithRetry(fullUrl, {
      method: 'GET',
      headers: this._buildHeaders(options.headers),
      ...options
    });
    
    return response.json();
  },
  
  /**
   * Makes a POST request
   * @param {string} url - Request URL (relative or absolute)
   * @param {Object} data - Request body data
   * @param {Object} options - Additional fetch options
   * @returns {Promise<any>}
   */
  async post(url, data = {}, options = {}) {
    const fullUrl = url.startsWith('http') ? url : `${this.BASE_URL}${url}`;
    
    const response = await this._fetchWithRetry(fullUrl, {
      method: 'POST',
      headers: this._buildHeaders(options.headers),
      body: JSON.stringify(data),
      ...options
    });
    
    return response.json();
  },
  
  /**
   * Makes a PUT request
   * @param {string} url - Request URL (relative or absolute)
   * @param {Object} data - Request body data
   * @param {Object} options - Additional fetch options
   * @returns {Promise<any>}
   */
  async put(url, data = {}, options = {}) {
    const fullUrl = url.startsWith('http') ? url : `${this.BASE_URL}${url}`;
    
    const response = await this._fetchWithRetry(fullUrl, {
      method: 'PUT',
      headers: this._buildHeaders(options.headers),
      body: JSON.stringify(data),
      ...options
    });
    
    return response.json();
  },
  
  /**
   * Makes a PATCH request
   * @param {string} url - Request URL (relative or absolute)
   * @param {Object} data - Request body data
   * @param {Object} options - Additional fetch options
   * @returns {Promise<any>}
   */
  async patch(url, data = {}, options = {}) {
    const fullUrl = url.startsWith('http') ? url : `${this.BASE_URL}${url}`;
    
    const response = await this._fetchWithRetry(fullUrl, {
      method: 'PATCH',
      headers: this._buildHeaders(options.headers),
      body: JSON.stringify(data),
      ...options
    });
    
    return response.json();
  },
  
  /**
   * Makes a DELETE request
   * @param {string} url - Request URL (relative or absolute)
   * @param {Object} options - Additional fetch options
   * @returns {Promise<any>}
   */
  async del(url, options = {}) {
    const fullUrl = url.startsWith('http') ? url : `${this.BASE_URL}${url}`;
    
    const response = await this._fetchWithRetry(fullUrl, {
      method: 'DELETE',
      headers: this._buildHeaders(options.headers),
      ...options
    });
    
    // DELETE might return 204 No Content
    if (response.status === 204) {
      return null;
    }
    
    return response.json();
  },
  
  /**
   * Shows a success toast
   * @param {string} message - Success message
   */
  showSuccess(message) {
    this._showToast(message, 'success');
  },
  
  /**
   * Shows an error toast
   * @param {string} message - Error message
   */
  showError(message) {
    this._showToast(message, 'error');
  },
  
  /**
   * Shows a warning toast
   * @param {string} message - Warning message
   */
  showWarning(message) {
    this._showToast(message, 'warning');
  },
  
  /**
   * Shows an info toast
   * @param {string} message - Info message
   */
  showInfo(message) {
    this._showToast(message, 'info');
  }
};

// Global window functions for easy access
window.api = ApiClient;

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ApiClient;
}
