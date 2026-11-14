/**
 * gametools.js - Script for handling game tools functionality in Avirta
 * 
 * This script handles:
 * 1. Double Points tool - Doubles the points for the next question
 * 2. Change Question tool - Changes the current question to a new one
 * 
 * These tools can be used by players during the game to enhance their gameplay experience.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize game tools functionality
    initializeGameTools();
});

/**
 * Initialize game tools functionality
 */
function initializeGameTools() {
    // Set up Double Points button in game_room.html and joined_room.html
    setupDoublePointsButton();

    // Set up Change Question button in question.html
    setupChangeQuestionButton();

    // Set up polling for tool usage events
    setupToolEventPolling();
}

/**
 * Update player tools based on game state
 * This function is called from livestatus.js
 */
window.avirtaUpdatePlayerTools = window.updatePlayerTools = function(data) {
    // Update Double Points button
    const doublePointsButton = document.querySelector('.dp');
    if (doublePointsButton && data.player_tools && data.player_tools.double_points !== undefined) {
        // Special handling for host: use current player's tools if available
        if (data.is_host) {
            // Determine which tools to use for the button state
            // If current_player_tools is available and it's not the host's turn, use those
            // Otherwise use the host's own tools
            const toolsToUse = (data.current_player_tools && data.current_player !== data.player_name) 
                ? data.current_player_tools.double_points 
                : data.player_tools.double_points;

            if (!toolsToUse) {
                // Tool was already used, disable it
                doublePointsButton.setAttribute('disabled', 'disabled');
                doublePointsButton.classList.add('is-used');
                doublePointsButton.title = 'Already used this game';
            } else {
                // Enable button for host
                doublePointsButton.removeAttribute('disabled');
                doublePointsButton.classList.remove('is-used');
                doublePointsButton.title = 'Double the points for the current player';
            }
        } else {
            // Regular player logic - only check if tool has been used
            if (!data.player_tools.double_points) {
                doublePointsButton.setAttribute('disabled', 'disabled');
                doublePointsButton.classList.add('is-used');
                doublePointsButton.title = 'Already used this game';
            } else {
                doublePointsButton.removeAttribute('disabled');
                doublePointsButton.classList.remove('is-used');
                doublePointsButton.title = 'Double the points for your next question';
            }
        }
    }

    // Update Change Question button (only on question page)
    const changeQuestionButton = document.getElementById('change-question-btn');
    if (changeQuestionButton && data.player_tools && data.player_tools.change_question !== undefined) {
        // Special handling for host: use current player's tools if available
        if (data.is_host) {
            // Determine which tools to use for the button state
            // If current_player_tools is available and it's not the host's turn, use those
            // Otherwise use the host's own tools
            const toolsToUse = (data.current_player_tools && data.current_player !== data.player_name) 
                ? data.current_player_tools.change_question 
                : data.player_tools.change_question;

            if (!toolsToUse) {
                // Tool was already used, disable it
                changeQuestionButton.setAttribute('disabled', 'disabled');
                changeQuestionButton.classList.add('is-used');
                changeQuestionButton.title = 'Already used this game';
            } else {
                // Enable button for host
                changeQuestionButton.removeAttribute('disabled');
                changeQuestionButton.classList.remove('is-used');
                changeQuestionButton.title = 'Change the question for the current player';
            }
        } else {
            // Regular player logic - only check if tool has been used
            if (!data.player_tools.change_question) {
                changeQuestionButton.setAttribute('disabled', 'disabled');
                changeQuestionButton.classList.add('is-used');
                changeQuestionButton.title = 'Already used this game';
            } else {
                changeQuestionButton.removeAttribute('disabled');
                changeQuestionButton.classList.remove('is-used');
                changeQuestionButton.title = 'Change to a different question';
            }
        }
    }
}

/**
 * Set up Double Points button
 */
function setupDoublePointsButton() {
    const doublePointsBtn = document.getElementById('double-points-btn');
    if (doublePointsBtn) {
        doublePointsBtn.addEventListener('click', function(e) {
            // Prevent default if this is a submit button in a form
            if (e && e.preventDefault) {
                e.preventDefault();
            }

            // Disable the button to prevent multiple clicks
            doublePointsBtn.disabled = true;
            doublePointsBtn.classList.add('is-used');

            // Get the current player from the page
            const gameRoomSection = document.querySelector('.page-section');
            const isHost = gameRoomSection && gameRoomSection.dataset.isHost === 'true';
            const playerName = gameRoomSection && gameRoomSection.dataset.playerName;

            // Get the current player from the red badge
            const currentPlayerElement = document.querySelector('.red-badge');
            const currentPlayer = currentPlayerElement ? currentPlayerElement.textContent : null;

            // Prepare the request body
            const formData = new FormData();
            formData.append('tool_name', 'double_points');

            // Determine if we need to include acting_player
            if (isHost && currentPlayer && currentPlayer !== playerName) {
                formData.append('acting_player', currentPlayer);
            }

            fetch('/use_tool', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: new URLSearchParams(formData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Notify game_room to refresh
                    fetch('/notify_game_room', { method: 'POST' });

                    // Add status update if the function exists
                    if (typeof addStatusUpdate === 'function') {
                        addStatusUpdate(data.message || 'Double Points activated!', 'status-warning');
                    }

                    // Disable the button permanently as the tool has been used
                    doublePointsBtn.disabled = true;
                    doublePointsBtn.classList.add('is-used');
                    doublePointsBtn.title = 'Already used this game';
                } else {
                    // Re-enable the button if there was an error
                    doublePointsBtn.disabled = false;
                    doublePointsBtn.classList.remove('is-used');

                    // Show error message
                    if (typeof showModal === 'function') {
                        showModal(data.message || 'Could not use Double Points tool.');
                    } else {
                        alert(data.message || 'Could not use Double Points tool.');
                    }
                }
            })
            .catch(error => {
                console.error('Error using Double Points tool:', error);

                // Re-enable the button if there was an error
                doublePointsBtn.disabled = false;
                doublePointsBtn.classList.remove('is-used');

                if (typeof showModal === 'function') {
                    showModal('Error using Double Points tool.');
                } else {
                    alert('Error using Double Points tool.');
                }
            });
        });
    }
}

/**
 * Set up Change Question button
 */
function setupChangeQuestionButton() {
    // Run this on both the question page and joined_room page
    if (!window.location.pathname.includes('/question/') && !window.location.pathname.includes('/joined_room')) {
        return;
    }

    // Variables for tracking question changes
    let questionChanged = false;
    let clientInitiatedChange = false;

    // Check if we just reloaded due to a question change
    if (localStorage.getItem('questionJustChanged') === 'true') {
        // Clear the flag
        localStorage.removeItem('questionJustChanged');
        // Set the flags to prevent further reloads
        questionChanged = true;
        clientInitiatedChange = true;
    }

    // Find all Change Question buttons
    const changeQuestionButtons = document.querySelectorAll('#change-question-btn');

    changeQuestionButtons.forEach(button => {
        // Add click event listener to the button
        button.addEventListener('click', function(e) {
            e.preventDefault();

            // Set flags BEFORE sending the request to prevent race conditions
            questionChanged = true;
            clientInitiatedChange = true;

            // Set a flag in localStorage to track across page reloads
            localStorage.setItem('questionJustChanged', 'true');

            // Disable the button to prevent multiple clicks
            button.disabled = true;
            button.classList.add('is-used');

            // Get the tool_name from the nearest input or use default
            const container = button.closest('.form-actions');
            const toolNameInput = container ? container.querySelector('input[name="tool_name"]') : null;
            const toolName = toolNameInput ? toolNameInput.value : 'change_question';

            // Get the acting_player from the nearest input or use default
            const actingPlayerInput = container ? container.querySelector('input[name="acting_player"]') : null;
            const actingPlayer = actingPlayerInput ? actingPlayerInput.value : null;

            // Prepare the request body
            const formData = new FormData();
            formData.append('tool_name', toolName);
            if (actingPlayer) {
                formData.append('acting_player', actingPlayer);
            }

            // Send AJAX request to use the Change Question tool
            fetch('/use_tool', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: new URLSearchParams(formData)
            })
            .then(response => {
                if (!response.ok) {
                    // Clear flags if request failed
                    localStorage.removeItem('questionJustChanged');
                    questionChanged = false;
                    clientInitiatedChange = false;
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // If there's a redirect URL, navigate to it
                    if (data.redirect) {
                        window.location.href = data.redirect;
                    } else {
                        // Reload the page to show the new question
                        window.location.reload();
                    }
                } else {
                    // Clear flags if request was not successful
                    localStorage.removeItem('questionJustChanged');
                    questionChanged = false;
                    clientInitiatedChange = false;

                    // Re-enable the button if there was an error
                    button.disabled = false;
                    button.classList.remove('is-used');
                    if (typeof showModal === 'function') {
                        showModal('Could not change question: ' + (data.message || ''));
                    } else {
                        alert('Could not change question: ' + (data.message || ''));
                    }
                }
            })
            .catch(error => {
                console.error('Error using Change Question tool:', error);

                // Clear flags if there was an error
                localStorage.removeItem('questionJustChanged');
                questionChanged = false;
                clientInitiatedChange = false;

                // Re-enable the button if there was an error
                button.disabled = false;
                button.classList.remove('is-used');
                if (typeof showModal === 'function') {
                    showModal('Error using Change Question tool.');
                } else {
                    alert('Error using Change Question tool.');
                }
            });
        });
    });
}

/**
 * Set up polling for tool usage events
 */
function setupToolEventPolling() {
    // Run this on both the question page and joined_room page
    if (!window.location.pathname.includes('/question/') && !window.location.pathname.includes('/joined_room')) {
        return;
    }

    const roomId = document.querySelector('.page-section')?.dataset.roomId;
    const currentPlayer = document.querySelector('.page-section')?.dataset.currentPlayer;

    if (!roomId || !currentPlayer) {
        return;
    }

    let lastEventTimestamp = null;
    let questionChanged = false;
    let clientInitiatedChange = false;

    // Store processed event IDs to prevent duplicate processing
    // Load previously processed events from localStorage
    let processedEventIds;
    try {
        const savedEvents = localStorage.getItem('processedEventIds');
        processedEventIds = new Set(savedEvents ? JSON.parse(savedEvents) : []);
    } catch (e) {
        console.error('Error loading processed events from localStorage:', e);
        processedEventIds = new Set();
    }

    // Function to poll for game updates
    function pollGameUpdates() {
        if (questionChanged) {
            return; // Stop polling if the question has been changed
        }

        fetch(`/api/game_updates/${roomId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                // Process events to check for change_question commands
                if (data.events && data.events.length > 0) {
                    // Get only new events since the last poll
                    const newEvents = lastEventTimestamp 
                        ? data.events.filter(event => event.timestamp > lastEventTimestamp)
                        : data.events;

                    // Update the last event timestamp
                    if (data.events.length > 0) {
                        const latestEvent = data.events[data.events.length - 1];
                        lastEventTimestamp = latestEvent.timestamp;
                    }

                    // Check for change_question events
                    for (const event of newEvents) {
                        // Create a unique ID for this event to prevent duplicate processing
                        const eventId = `${event.type}_${event.timestamp}_${event.data.player_name || ''}_${event.data.tool_name || ''}`;

                        // Skip if we've already processed this event
                        if (processedEventIds.has(eventId)) {
                            continue;
                        }

                        // Mark this event as processed
                        processedEventIds.add(eventId);

                        // Save updated processed events to localStorage
                        try {
                            localStorage.setItem('processedEventIds', JSON.stringify([...processedEventIds]));
                        } catch (e) {
                            console.error('Error saving processed events to localStorage:', e);
                        }

                        if (event.type === 'tool_used') {
                            // Handle change_question command from the current player
                            if (event.data.tool_name === 'change_question' && 
                                event.data.player_name === currentPlayer && 
                                !clientInitiatedChange) {
                                console.log('Current player changed the question');
                                questionChanged = true;

                                // Set a flag in localStorage to prevent refresh loops
                                localStorage.setItem('questionJustChanged', 'true');

                                // Reload the page to show the new question
                                window.location.reload();
                                return;
                            }
                        }
                    }
                }
            })
            .catch(error => {
                console.error('Error fetching game updates:', error);
            });
    }

    // Poll for updates every 1 second
    pollGameUpdates(); // Initial poll
    const pollInterval = setInterval(pollGameUpdates, 1000);

    // Clean up interval when the page is unloaded
    window.addEventListener('beforeunload', function(e) {
        clearInterval(pollInterval);

        // If we're navigating away (not reloading due to a question change),
        // clear the processed events to prevent the set from growing too large
        if (!questionChanged) {
            localStorage.removeItem('processedEventIds');
        }
    });
}
