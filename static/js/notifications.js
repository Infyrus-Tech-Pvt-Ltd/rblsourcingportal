/**
 * Reusable Notification System
 * Handles both server-side flash messages and client-side notifications
 */

class NotificationSystem {
  constructor() {
    this.init();
  }

  init() {
    // Create notification container if it doesn't exist
    this.createContainer();
    
    // Process any existing flash messages from server
    this.processFlashMessages();
    
    // Auto-hide notifications after delay
    this.autoHideNotifications();
  }

  createContainer() {
    if (!document.getElementById('notification-container')) {
      const container = document.createElement('div');
      container.id = 'notification-container';
      container.className = 'fixed top-4 right-4 z-50 space-y-3 max-w-md';
      document.body.appendChild(container);
    }
  }

  processFlashMessages() {
    // Look for flash messages in data attributes or hidden elements
    const flashData = document.querySelector('[data-flash-messages]');
    if (flashData) {
      try {
        const messages = JSON.parse(flashData.getAttribute('data-flash-messages'));
        messages.forEach(([category, message]) => {
          this.show(message, category, 5000);
        });
      } catch (e) {
        console.warn('Error parsing flash messages:', e);
      }
    }
  }

  show(message, type = 'info', duration = 5000) {
    const notification = this.createNotification(message, type);
    const container = document.getElementById('notification-container');
    
    // Add notification with animation
    container.appendChild(notification);
    
    // Trigger entrance animation
    setTimeout(() => {
      notification.classList.remove('translate-x-full', 'opacity-0');
      notification.classList.add('translate-x-0', 'opacity-100');
    }, 10);

    // Auto remove after duration
    if (duration > 0) {
      setTimeout(() => {
        this.hide(notification);
      }, duration);
    }

    return notification;
  }

  createNotification(message, type) {
    const notification = document.createElement('div');
    notification.className = `
      transform transition-all duration-300 ease-in-out translate-x-full opacity-0
      bg-white rounded-lg shadow-lg border-l-4 p-4 min-w-80 max-w-md
      ${this.getTypeClasses(type)}
    `;

    const icon = this.getIcon(type);
    const closeButton = this.createCloseButton();

    notification.innerHTML = `
      <div class="flex items-start">
        <div class="flex-shrink-0">
          ${icon}
        </div>
        <div class="ml-3 flex-1">
          <p class="text-sm font-medium ${this.getTextColor(type)}">${message}</p>
        </div>
        <div class="ml-4 flex-shrink-0">
          ${closeButton}
        </div>
      </div>
    `;

    // Add click handler for close button
    notification.querySelector('.close-btn').addEventListener('click', () => {
      this.hide(notification);
    });

    return notification;
  }

  getTypeClasses(type) {
    const classes = {
      'success': 'border-green-400',
      'error': 'border-red-400',
      'warning': 'border-yellow-400',
      'info': 'border-blue-400'
    };
    return classes[type] || classes['info'];
  }

  getTextColor(type) {
    const colors = {
      'success': 'text-green-800',
      'error': 'text-red-800',
      'warning': 'text-yellow-800',
      'info': 'text-blue-800'
    };
    return colors[type] || colors['info'];
  }

  getIcon(type) {
    const icons = {
      'success': `
        <svg class="w-5 h-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
        </svg>
      `,
      'error': `
        <svg class="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
        </svg>
      `,
      'warning': `
        <svg class="w-5 h-5 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
        </svg>
      `,
      'info': `
        <svg class="w-5 h-5 text-blue-400" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path>
        </svg>
      `
    };
    return icons[type] || icons['info'];
  }

  createCloseButton() {
    return `
      <button type="button" class="close-btn rounded-md p-1.5 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-400 transition-colors">
        <svg class="w-4 h-4 text-gray-400" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
        </svg>
      </button>
    `;
  }

  hide(notification) {
    notification.classList.remove('translate-x-0', 'opacity-100');
    notification.classList.add('translate-x-full', 'opacity-0');
    
    setTimeout(() => {
      if (notification.parentNode) {
        notification.parentNode.removeChild(notification);
      }
    }, 300);
  }

  autoHideNotifications() {
    // Hide notifications when clicking outside
    document.addEventListener('click', (e) => {
      if (!e.target.closest('#notification-container')) {
        const notifications = document.querySelectorAll('#notification-container > div');
        notifications.forEach(notification => {
          if (notification.classList.contains('opacity-100')) {
            // Only auto-hide if it's been visible for at least 2 seconds
            setTimeout(() => this.hide(notification), 100);
          }
        });
      }
    });
  }

  // Convenience methods
  success(message, duration = 5000) {
    return this.show(message, 'success', duration);
  }

  error(message, duration = 7000) {
    return this.show(message, 'error', duration);
  }

  warning(message, duration = 6000) {
    return this.show(message, 'warning', duration);
  }

  info(message, duration = 5000) {
    return this.show(message, 'info', duration);
  }

  // Clear all notifications
  clear() {
    const container = document.getElementById('notification-container');
    if (container) {
      container.innerHTML = '';
    }
  }
}

// Initialize global notification system
window.notifications = new NotificationSystem();

// Expose convenience methods globally
window.showNotification = (message, type, duration) => window.notifications.show(message, type, duration);
window.showSuccess = (message, duration) => window.notifications.success(message, duration);
window.showError = (message, duration) => window.notifications.error(message, duration);
window.showWarning = (message, duration) => window.notifications.warning(message, duration);
window.showInfo = (message, duration) => window.notifications.info(message, duration);
