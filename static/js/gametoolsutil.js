/**
 * gametoolsutil.js - Utility functions for game tools in Avirta
 * 
 * This script provides utility functions for game tools:
 * 1. updatePlayerTools - Updates player tools based on game state
 * 2. addStatusUpdate - Adds a status update manually (for tool usage feedback)
 */

/**
 * Update player tools based on game state
 * This function is called from livestatus.js
 */
// Not a global named "updatePlayerTools": this file is loaded after gametools.js,
// and a global function declaration with that name would replace gametools.js's
// window.updatePlayerTools with this wrapper, which then calls itself forever.
function updatePlayerToolsUtil(data) {
    var impl = window.avirtaUpdatePlayerTools || window.updatePlayerTools;
    if (typeof impl === 'function' && impl !== updatePlayerToolsUtil) {
        impl(data);
    }
}

/**
 * Add a status update manually (for tool usage feedback)
 * @param {string} message - The message to display
 * @param {string} type - The type of message (default, status-success, status-error, status-warning, status-info)
 */
function addStatusUpdate(message, type = 'default') {
    const statusUpdates = document.getElementById('status-updates');
    if (!statusUpdates) return;

    const statusMessage = document.createElement('p');
    statusMessage.className = `status-message ${type}`;

    // Add timestamp
    const timestamp = new Date().toLocaleTimeString();
    statusMessage.textContent = `[${timestamp}] ${message}`;

    // Add to the top of the list
    statusUpdates.insertBefore(statusMessage, statusUpdates.firstChild);

    // Limit the number of status updates to 20
    while (statusUpdates.children.length > 20) {
        statusUpdates.removeChild(statusUpdates.lastChild);
    }
}

// Export functions to window object for global access
window.updatePlayerToolsUtil = updatePlayerToolsUtil;
window.addStatusUpdate = addStatusUpdate;