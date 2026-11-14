/**
 * Avirta Game - Main JavaScript File
 * 
 * This file contains client-side functionality for the Avirta game.
 */

// Global settings

// Modal queue system
let modalQueue = [];
let currentModal = null;
let isModalActive = false;

// Wait for the DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('Avirta game interface loaded');

    // Initialize any interactive elements
    initializeGameInterface();

    // Setup flash messages
    setupFlashMessages();

    // Setup scroll position saving (defined by the game pages that need it)
    if (typeof setupScrollPositionSaving === 'function') {
        setupScrollPositionSaving();
    }
});

/**
 * Initialize the game interface elements
 */
function initializeGameInterface() {
    // Add event listeners to category checkboxes (limit to max_categories selections)
    const categoryCheckboxes = document.querySelectorAll('input[name="categories"]');
    if (categoryCheckboxes.length > 0) {
        // Get the maximum number of categories from the form's data attribute
        const form = document.querySelector('form[action*="create_room"]');
        const maxCategories = form ? parseInt(form.getAttribute('data-max-categories')) || 7 : 7;

        categoryCheckboxes.forEach(checkbox => {
            checkbox.addEventListener('change', function() {
                const checked = document.querySelectorAll('input[name="categories"]:checked');
                if (checked.length > maxCategories) {
                    this.checked = false;
                    showModal(`You can select a maximum of ${maxCategories} categories.`);
                }
            });
        });
    }

    // Add timer functionality for questions if needed
    setupQuestionTimer();

    // Add any other interactive elements
    setupFormValidation();
}

/**
 * Set up a timer for answering questions
 */
function setupQuestionTimer() {
    // Skip timer functionality for the Fastest game mode
    if (window.location.pathname.includes('/fastest/')) {
        return; // Don't add timer functionality to Fastest game pages
    }

    const questionSection = document.querySelector('.question-display');
    if (!questionSection) return; // Not on a question page

    // Get the default time limit from the cookie or use 30 seconds as fallback
    let timeLeft = getCookie('default_time_limit') ? parseInt(getCookie('default_time_limit')) : 30;

    // Helper function to get cookie value
    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
    }
    const timerDisplay = document.createElement('div');
    timerDisplay.className = 'timer';
    timerDisplay.innerHTML = `Time remaining: <span id="time-left">${timeLeft}</span> seconds`;

    // Insert the timer at the top of the question section
    questionSection.insertBefore(timerDisplay, questionSection.firstChild);

    // Start the countdown
    let timerInterval = null;
    // Lets the page freeze the countdown, e.g. once a text answer is revealed.
    window.stopQuestionTimer = function () {
        if (timerInterval) {
            clearInterval(timerInterval);
            timerInterval = null;
            timerDisplay.classList.add('timer-stopped');
        }
    };
    timerInterval = setInterval(function() {
        timeLeft--;
        document.getElementById('time-left').textContent = timeLeft;

        if (timeLeft <= 0) {
            clearInterval(timerInterval);
            timerInterval = null;

            // Check if this is a text-based question
            const showAnswerBtn = document.getElementById('show-answer-btn');
            const evaluateForm = document.querySelector('form[action*="evaluate_answer"]');

            // Auto-submit the form when time runs out
            const form = document.querySelector('.answer-form');

            if (form) {
                // For multiple choice or true/false questions
                showModal('Time\'s up! Submitting your answer...', () => {
                    form.submit();
                });
            } else if (showAnswerBtn && evaluateForm) {
                // For text-based questions
                // First show the answer
                showAnswer();

                // Then submit the form with "incorrect" evaluation after a short delay
                showModal('Time\'s up! Marking as incorrect...', () => {
                    // Find the "incorrect" button and click it
                    const incorrectButton = evaluateForm.querySelector('button[value="incorrect"]');
                    if (incorrectButton) {
                        incorrectButton.click();
                    }
                });
            }
        }
    }, 1000);
}

/**
 * Set up form validation for various forms
 */
function setupFormValidation() {
    // Example: Validate the join room form
    const joinRoomForm = document.querySelector('form[action*="join_room"]');
    if (joinRoomForm) {
        joinRoomForm.addEventListener('submit', function(event) {
            const roomIdInput = document.getElementById('room_id');
            const playerNameInput = document.getElementById('player_name');

            if (roomIdInput && !roomIdInput.value.trim()) {
                event.preventDefault();
                showModal('Please enter a Room ID.');
                return false;
            }

            if (playerNameInput && !playerNameInput.value.trim()) {
                event.preventDefault();
                showModal('Please enter your name.');
                return false;
            }
        });
    }

    // Example: Validate the create room form
    const createRoomForm = document.querySelector('form[action*="create_room"]');
    if (createRoomForm) {
        createRoomForm.addEventListener('submit', function(event) {
            const roomNameInput = document.getElementById('room_name');
            const hostNameInput = document.getElementById('host_name');

            if (roomNameInput && !roomNameInput.value.trim()) {
                event.preventDefault();
                showModal('Please enter a Room Name.');
                return false;
            }

            if (hostNameInput && !hostNameInput.value.trim()) {
                event.preventDefault();
                showModal('Please enter your name.');
                return false;
            }

            // Only enforce category selection if this form actually contains category checkboxes
            const categoryInputs = this.querySelectorAll('input[name="categories"]');
            if (categoryInputs.length > 0) {
                const checkedCount = this.querySelectorAll('input[name="categories"]:checked').length;
                if (checkedCount === 0) {
                    event.preventDefault();
                    showModal('Please select at least one category.يرجى اختيار مجموعة واحدة على الأقل');
                    return false;
                }
            }
        });
    }
}

/**
 * Handle flash messages
 */
function setupFlashMessages() {
    // Timing now lives in ui.js (initFlashes): errors stay until dismissed,
    // other messages leave after a few seconds. Nothing to do here.
}

/**
 * Process the next modal in the queue
 */
function processModalQueue() {
    // If there's already a modal active or no modals in queue, return
    if (isModalActive || modalQueue.length === 0) {
        return;
    }
    
    // Get the next modal from the queue
    const nextModal = modalQueue.shift();
    
    // Display the modal
    displayModalNow(nextModal.message, nextModal.callback);
}

/**
 * Close a modal dialog
 * @param {HTMLElement} [modalElement] - The modal element to close (optional)
 * If not provided, closes the most recently opened modal
 */
function closeModal(modalElement) {
    // If no specific modal is provided, get the most recently added modal
    const modalToClose = modalElement || currentModal || document.querySelector('.modal');

    if (!modalToClose) return; // No modal to close

    // Apply fade-out animation
    modalToClose.classList.add('fade-out');

    // Wait for the fade-out to complete before hiding the modal
    setTimeout(() => {
        modalToClose.style.display = 'none'; // Hide modal after animation finishes
        modalToClose.classList.remove('fade-out'); // Remove fade-out class for reuse

        // Remove the modal element if necessary
        if (modalToClose.parentNode) {
            modalToClose.parentNode.removeChild(modalToClose);
        }

        // Execute callback if it exists
        const callback = modalToClose._callback;
        if (typeof callback === 'function') {
            callback();
        }

        // Reset modal state
        currentModal = null;
        isModalActive = false;

        // Process the next modal in the queue
        processModalQueue();
    }, 300); // Use a shorter timeout for fade-out animation (300ms)
}

/**
 * Actually display a modal (internal function used by the queue system)
 * @param {string} message - The message to display in the modal
 * @param {Function} callback - Optional callback function to execute after the modal is closed
 */
function displayModalNow(message, callback) {
    // Set modal as active
    isModalActive = true;
    
    // Create modal elements
    const modalOverlay = document.createElement('div');
    modalOverlay.className = 'modal';

    // Store the callback on the modal element for later use
    modalOverlay._callback = callback;

    const modalContent = document.createElement('div');
    modalContent.className = 'modal-content';

    const closeButton = document.createElement('span');
    //closeButton.className = 'close-modal';
    //closeButton.innerHTML = '&times;';
    //closeButton.title = 'Close';

    const messageElement = document.createElement('p');
    messageElement.innerHTML = message;

    // Assemble the modal
    modalContent.appendChild(closeButton);
    modalContent.appendChild(messageElement);
    modalOverlay.appendChild(modalContent);

    // Add to the document
    document.body.appendChild(modalOverlay);

    // Store reference to current modal
    currentModal = modalOverlay;

    // Display the modal
    modalOverlay.style.display = 'block';

    // Event listeners for closing the modal
    closeButton.addEventListener('click', () => closeModal(modalOverlay));
    modalOverlay.addEventListener('click', (event) => {
        if (event.target === modalOverlay) {
            closeModal(modalOverlay);
        }
    });

    // Allow closing with Escape key
    document.addEventListener('keydown', function escapeHandler(event) {
        if (event.key === 'Escape') {
            closeModal(modalOverlay);
            document.removeEventListener('keydown', escapeHandler);
        }
    });
}

/**
 * Display a styled modal dialog instead of using the browser's alert()
 * This function uses a queue system to ensure only one modal is displayed at a time
 * @param {string} message - The message to display in the modal
 * @param {Function} callback - Optional callback function to execute after the modal is closed
 */
function showModal(message, callback) {
    // If no modal is currently active, display immediately
    if (!isModalActive) {
        displayModalNow(message, callback);
    } else {
        // Add to queue if a modal is already active
        modalQueue.push({ message: message, callback: callback });
    }
}

/**
 * This file can be expanded with additional functionality as needed.
 * Potential enhancements:
 * - Real-time updates using WebSockets
 * - Animations for question transitions
 * - Sound effects for correct/incorrect answers
 * - Local storage for game history
 */
