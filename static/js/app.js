// Bluesky Timeline App JavaScript

// Global app state
const AppState = {
    posts: [],
    isLoading: false,
    currentCount: 9,
    lastRefresh: null
};

// Utility functions
const Utils = {
    // Escape HTML to prevent XSS
    escapeHtml: function(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    // Format file size
    formatFileSize: function(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    // Format date
    formatDate: function(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;
        
        return date.toLocaleDateString();
    },

    // Debounce function
    debounce: function(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
};

// API service
const ApiService = {
    baseUrl: '',

    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const config = {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        };

        try {
            const response = await fetch(url, config);
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || `HTTP ${response.status}`);
            }
            
            return data;
        } catch (error) {
            console.error(`API request failed: ${endpoint}`, error);
            throw error;
        }
    },

    async getPosts(count = 5) {
        return this.request(`/api/posts?count=${count}`);
    },

    async getStatus() {
        return this.request('/api/status');
    },

    async getUserInfo() {
        return this.request('/api/user');
    },

    async generateMagicResponse(postIndex, imageFilenames, postText, imageAltTexts) {
        return this.request('/api/magic-response', {
            method: 'POST',
            body: JSON.stringify({
                post_index: postIndex,
                image_filenames: imageFilenames,
                post_text: postText,
                image_alt_texts: imageAltTexts
            })
        });
    },

    getImageUrl(filename) {
        return `/api/image/${filename}`;
    }
};

// UI components
const UI = {
    // Show loading state
    showLoading: function() {
        document.getElementById('loading').style.display = 'block';
        document.getElementById('error-alert').style.display = 'none';
        document.getElementById('posts-container').innerHTML = '';
        document.getElementById('empty-state').style.display = 'none';
        AppState.isLoading = true;
    },

    // Show progress state
    showProgress: function(message, progressPercent = 0, postsFound = 0, postsChecked = 0, currentBatch = 0) {
        const loadingElement = document.getElementById('loading');
        const progressBar = loadingElement.querySelector('.progress-bar');
        const progressText = loadingElement.querySelector('.progress-text');
        
        if (progressBar) {
            progressBar.style.width = `${progressPercent}%`;
            progressBar.setAttribute('aria-valuenow', progressPercent);
        }
        
        if (progressText) {
            progressText.innerHTML = `
                <h4 class="text-primary mb-2">${message}</h4>
                <p class="text-muted mb-2">Found ${postsFound} posts with images • Checked ${postsChecked} total posts • Batch ${currentBatch}</p>
                <div class="progress mt-3" style="height: 8px;">
                    <div class="progress-bar progress-bar-striped progress-bar-animated bg-primary" 
                         role="progressbar" 
                         style="width: ${progressPercent}%" 
                         aria-valuenow="${progressPercent}" 
                         aria-valuemin="0" 
                         aria-valuemax="100">
                    </div>
                </div>
            `;
        }
    },

    // Hide loading state
    hideLoading: function() {
        document.getElementById('loading').style.display = 'none';
        AppState.isLoading = false;
    },

    // Show error message
    showError: function(message) {
        const errorAlert = document.getElementById('error-alert');
        const errorMessage = document.getElementById('error-message');
        errorMessage.textContent = message;
        errorAlert.style.display = 'block';
    },

    // Hide error message
    hideError: function() {
        document.getElementById('error-alert').style.display = 'none';
    },

    // Update status indicator
    updateStatus: function(isConnected) {
        const statusIndicator = document.getElementById('status-indicator');
        if (isConnected) {
            statusIndicator.innerHTML = '<i class="fas fa-circle text-success"></i> Connected';
        } else {
            statusIndicator.innerHTML = '<i class="fas fa-circle text-danger"></i> Disconnected';
        }
    },

    // Update username display
    updateUsername: function(userInfo) {
        const usernameElement = document.getElementById('username-display');
        if (usernameElement && userInfo) {
            usernameElement.innerHTML = `
                <i class="fas fa-user me-1"></i>
                <span class="fw-bold">${userInfo.display_name}</span>
                <small class="text-muted">@${userInfo.handle}</small>
            `;
        }
    },

    // Create post card HTML
    createPostCard: function(post, index) {
        const postDate = Utils.formatDate(post.post.indexed_at);
        const images = post.embeds.filter(embed => embed.type === 'image');
        
        return `
            <div class="card mb-4 shadow-sm" data-post-index="${index}">
                <div class="card-header bg-light">
                    <div class="d-flex align-items-center justify-content-between">
                        <div>
                            <h6 class="mb-0">${Utils.escapeHtml(post.author.display_name)}</h6>
                            <small class="text-muted">@${Utils.escapeHtml(post.author.handle)}</small>
                        </div>
                        <small class="text-muted">${postDate}</small>
                    </div>
                </div>
                <div class="card-body">
                    <p class="card-text">${Utils.escapeHtml(post.post.text).replace(/\n/g, '<br>')}</p>
                    
                    ${images.length > 0 ? this.createImagesSection(images) : ''}
                    
                    <div class="d-flex justify-content-between align-items-center mt-auto">
                        <div class="engagement-stats">
                            <span class="engagement-item" title="Replies">
                                <i class="fas fa-reply"></i> ${post.post.reply_count}
                            </span>
                            <span class="engagement-item" title="Reposts">
                                <i class="fas fa-retweet"></i> ${post.post.repost_count}
                            </span>
                            <span class="engagement-item" title="Likes">
                                <i class="fas fa-heart"></i> ${post.post.like_count}
                            </span>
                        </div>
                        <div class="d-flex gap-2">
                            ${images.length > 0 ? `
                                <button class="btn btn-outline-warning btn-sm magic-btn" 
                                        onclick="UI.generateMagicResponse(${index})" 
                                        title="Generate smart AI reply to images and post content"
                                        data-post-index="${index}">
                                    <i class="fas fa-brain"></i> Smart Reply
                                </button>
                            ` : ''}
                            <a href="https://bsky.app/profile/${post.author.handle}/post/${post.post.uri.split('/').pop()}" 
                               target="_blank" class="btn btn-outline-primary btn-sm" title="View on Bluesky">
                                <i class="fas fa-external-link-alt"></i> View on Bluesky
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        `;
    },

    // Create images section HTML
    createImagesSection: function(images) {
        const colClass = images.length === 1 ? '12' : images.length === 2 ? '6' : '4';
        
        return `
            <div class="row g-2 mt-3">
                ${images.map(image => `
                    <div class="col-md-${colClass}">
                        <div class="image-container">
                            <img src="${ApiService.getImageUrl(image.filename)}" 
                                 class="img-fluid rounded shadow-sm" 
                                 alt="${Utils.escapeHtml(image.alt_text)}"
                                 onclick="UI.openImageModal('${image.filename}', '${Utils.escapeHtml(image.alt_text)}')"
                                 style="cursor: pointer;"
                                 loading="lazy">
                            ${image.alt_text ? `<small class="text-muted d-block mt-1">${Utils.escapeHtml(image.alt_text)}</small>` : ''}
                            <small class="text-muted d-block">
                                ${image.info.width}×${image.info.height} • 
                                ${Utils.formatFileSize(image.info.file_size)}
                            </small>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    },

    // Display posts
    displayPosts: function(posts) {
        const postsContainer = document.getElementById('posts-container');
        const emptyState = document.getElementById('empty-state');
        
        if (posts.length === 0) {
            emptyState.style.display = 'block';
            return;
        }
        
        AppState.posts = posts;
        postsContainer.innerHTML = posts.map((post, index) => this.createPostCard(post, index)).join('');
        
        // Add animation delay to each card
        const cards = postsContainer.querySelectorAll('.card');
        cards.forEach((card, index) => {
            card.style.animationDelay = `${index * 0.1}s`;
        });
    },

    // Display posts progressively with animation (one by one)
    displayPostsProgressively: function(posts) {
        const postsContainer = document.getElementById('posts-container');
        const emptyState = document.getElementById('empty-state');
        
        if (posts.length === 0) {
            emptyState.style.display = 'block';
            return;
        }
        
        // Clear container
        postsContainer.innerHTML = '';
        
        // Add posts one by one with a slight delay
        posts.forEach((post, index) => {
            setTimeout(() => {
                const postElement = document.createElement('div');
                postElement.innerHTML = this.createPostCard(post, index);
                postElement.className = 'post-card';
                
                postsContainer.appendChild(postElement);
                
                // Trigger animation
                setTimeout(() => {
                    postElement.classList.add('loaded');
                }, 50);
            }, index * 150); // 150ms delay between each post
        });
    },

    // Open image modal
    openImageModal: function(filename, altText) {
        // Create modal if it doesn't exist
        let modal = document.getElementById('imageModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'imageModal';
            modal.className = 'modal fade';
            modal.innerHTML = `
                <div class="modal-dialog modal-lg modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">Image Preview</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body text-center">
                            <img id="modalImage" class="img-fluid" alt="">
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }
        
        // Set image source and show modal
        document.getElementById('modalImage').src = ApiService.getImageUrl(filename);
        document.getElementById('modalImage').alt = altText;
        
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    },

    // Generate magic response for a post
    generateMagicResponse: async function(postIndex) {
        const post = AppState.posts[postIndex];
        if (!post) {
            console.error('Post not found for index:', postIndex);
            return;
        }

        const images = post.embeds.filter(embed => embed.type === 'image');
        if (images.length === 0) {
            console.error('No images found for post:', postIndex);
            return;
        }

        const magicBtn = document.querySelector(`[data-post-index="${postIndex}"]`);
        if (!magicBtn) {
            console.error('Magic button not found for post:', postIndex);
            return;
        }

        // Show loading state
        const originalContent = magicBtn.innerHTML;
        magicBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Thinking...';
        magicBtn.disabled = true;

        try {
            const imageFilenames = images.map(img => img.filename);
            const imageAltTexts = images.map(img => img.alt_text || '');
            const postText = post.post.text || '';
            
            const response = await ApiService.generateMagicResponse(postIndex, imageFilenames, postText, imageAltTexts);
            
            // Show the smart reply in a modal
            this.showMagicResponseModal(response.magic_response, post, images);
            
        } catch (error) {
            console.error('Error generating magic response:', error);
            this.showError('Failed to generate magic response: ' + error.message);
        } finally {
            // Restore button state
            magicBtn.innerHTML = originalContent;
            magicBtn.disabled = false;
        }
    },

    // Show magic response modal
    showMagicResponseModal: function(magicResponse, post, images) {
        // Create modal if it doesn't exist
        let modal = document.getElementById('magicResponseModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'magicResponseModal';
            modal.className = 'modal fade';
            modal.innerHTML = `
                <div class="modal-dialog modal-lg modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">
                                <i class="fas fa-brain me-2"></i>AI Smart Reply
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="mb-3">
                                <h6 class="text-muted">Original Post by @${Utils.escapeHtml(post.author.handle)}</h6>
                                <p class="small text-muted">${Utils.escapeHtml(post.post.text)}</p>
                            </div>
                            <div class="magic-response-content">
                                <h6 class="text-warning mb-3">
                                    <i class="fas fa-brain me-2"></i>Smart AI Reply:
                                </h6>
                                <div class="magic-response-text p-3 bg-light rounded">
                                    <p class="mb-0" id="magicResponseText"></p>
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                            <button type="button" class="btn btn-warning" onclick="UI.copyMagicResponse()">
                                <i class="fas fa-copy"></i> Copy Response
                            </button>
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }
        
        // Set the magic response text
        document.getElementById('magicResponseText').textContent = magicResponse;
        
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    },

    // Copy magic response to clipboard
    copyMagicResponse: function() {
        const responseText = document.getElementById('magicResponseText').textContent;
        navigator.clipboard.writeText(responseText).then(() => {
            // Show success feedback
            const copyBtn = document.querySelector('#magicResponseModal .btn-warning');
            const originalText = copyBtn.innerHTML;
            copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
            copyBtn.classList.remove('btn-warning');
            copyBtn.classList.add('btn-success');
            
            setTimeout(() => {
                copyBtn.innerHTML = originalText;
                copyBtn.classList.remove('btn-success');
                copyBtn.classList.add('btn-warning');
            }, 2000);
        }).catch(err => {
            console.error('Failed to copy text: ', err);
            this.showError('Failed to copy response to clipboard');
        });
    }
};

// Main app controller
const App = {
    // Initialize the app
    init: function() {
        console.log('App initializing...');
        this.setupEventListeners();
        // Load user info, posts, and check status
        this.loadUserInfo();
        this.loadPostsWithProgress().catch(error => {
            console.error('Failed to load posts on init:', error);
        });
        this.checkStatus();
    },

    // Setup event listeners
    setupEventListeners: function() {
        // Refresh button
        document.getElementById('refresh-btn').addEventListener('click', () => {
            this.loadPostsWithProgress();
        });

        // Post count radio buttons
        document.querySelectorAll('input[name="postCount"]').forEach(radio => {
            radio.addEventListener('change', (e) => {
                if (e.target.checked) {
                    AppState.currentCount = parseInt(e.target.value);
                    this.loadPostsWithProgress();
                }
            });
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'r' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                this.loadPostsWithProgress();
            }
        });
    },

    // Check bot status
    async checkStatus() {
        try {
            const data = await ApiService.getStatus();
            UI.updateStatus(data.initialized);
        } catch (error) {
            console.error('Status check failed:', error);
            UI.updateStatus(false);
        }
    },

    // Load user information
    async loadUserInfo() {
        try {
            const userInfo = await ApiService.getUserInfo();
            UI.updateUsername(userInfo);
        } catch (error) {
            console.error('Failed to load user info:', error);
        }
    },

    // Load posts from API
    async loadPosts() {
        if (AppState.isLoading) {
            console.log('Already loading posts, skipping...');
            return;
        }

        console.log('Loading posts...', { count: AppState.currentCount });
        UI.showLoading();
        
        try {
            const data = await ApiService.getPosts(AppState.currentCount);
            console.log('Posts loaded:', data);
            
            // Use progressive loading to show posts one by one
            if (data.posts && data.posts.length > 0) {
                UI.displayPostsProgressively(data.posts);
                AppState.lastRefresh = new Date();
                UI.hideError();
            } else {
                console.log('No posts found');
                UI.displayPosts([]);
            }
        } catch (error) {
            console.error('Error loading posts:', error);
            UI.showError(error.message);
        } finally {
            UI.hideLoading();
        }
    },

    // Load posts with streaming progress
    async loadPostsWithProgress() {
        if (AppState.isLoading) {
            console.log('Already loading posts, skipping...');
            return;
        }

        console.log('Loading posts with progress...', { count: AppState.currentCount });
        UI.showLoading();
        
        try {
            const eventSource = new EventSource(`/api/posts/stream?count=${AppState.currentCount}&max_per_user=1`);
            
            eventSource.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    console.log('Progress update:', data);
                    
                    switch (data.type) {
                        case 'start':
                            UI.showProgress(data.message, 0, 0, 0, 0);
                            break;
                            
                        case 'progress':
                            UI.showProgress(
                                data.message, 
                                data.progress_percent || 0, 
                                data.posts_found || 0, 
                                data.posts_checked || 0, 
                                data.current_batch || 0
                            );
                            break;
                            
                        case 'complete':
                            console.log('Posts loaded:', data);
                            if (data.posts && data.posts.length > 0) {
                                UI.displayPostsProgressively(data.posts);
                                AppState.lastRefresh = new Date();
                                UI.hideError();
                            } else {
                                console.log('No posts found');
                                UI.displayPosts([]);
                            }
                            eventSource.close();
                            UI.hideLoading();
                            break;
                            
                        case 'error':
                            console.error('Stream error:', data.error);
                            UI.showError(data.error);
                            eventSource.close();
                            UI.hideLoading();
                            break;
                    }
                } catch (error) {
                    console.error('Error parsing progress data:', error);
                }
            };
            
            eventSource.onerror = function(error) {
                console.error('EventSource error:', error);
                UI.showError('Connection lost while fetching posts');
                eventSource.close();
                UI.hideLoading();
            };
            
        } catch (error) {
            console.error('Error setting up stream:', error);
            UI.showError(error.message);
            UI.hideLoading();
        }
    }
};

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, initializing app...');
    App.init();
});

// Fallback initialization in case DOMContentLoaded already fired
if (document.readyState === 'loading') {
    // DOM is still loading, wait for DOMContentLoaded
} else {
    // DOM is already loaded, initialize immediately
    console.log('DOM already loaded, initializing app immediately...');
    App.init();
}

// Global functions for template compatibility
window.loadPosts = () => App.loadPostsWithProgress();
window.toggleTheme = () => {
    const currentTheme = document.documentElement.getAttribute('data-bs-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
    localStorage.setItem('theme', newTheme);
};

function setTheme(theme) {
    document.documentElement.setAttribute('data-bs-theme', theme);
    const themeIcon = document.getElementById('theme-icon');
    if (theme === 'dark') {
        themeIcon.className = 'fas fa-sun';
    } else {
        themeIcon.className = 'fas fa-moon';
    }
}

// Export for global access
window.UI = UI;
window.App = App;
