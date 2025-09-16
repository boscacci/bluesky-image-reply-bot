// Bluesky Timeline App JavaScript

// Global app state
const AppState = {
    posts: [],
    isLoading: false,
    currentCount: parseInt(localStorage.getItem('postCount') || '9'),
    lastRefresh: null,
    carouselIndex: {},
    previousPosts: [],
    wasFetchMore: false
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

    async generateAiReply(postIndex, imageFilenames, postText, imageAltTexts, themeConfig) {
        return this.request('/api/ai-reply', {
            method: 'POST',
            body: JSON.stringify({
                post_index: postIndex,
                image_filenames: imageFilenames,
                post_text: postText,
                image_alt_texts: imageAltTexts,
                theme_config: themeConfig
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
                    <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
                        <div>
                            <h6 class="mb-0">${Utils.escapeHtml(post.author.display_name)}</h6>
                            <small class="text-muted">@${Utils.escapeHtml(post.author.handle)}</small>
                        </div>
                        <div class="d-flex align-items-center gap-2">
                            <small class="text-muted me-2">${postDate}</small>
                            ${images.length > 0 ? `
                                <button class="btn btn-outline-success btn-sm ai-reply-btn" 
                                        onclick="UI.generateAiReply(${index})" 
                                        title="Generate themed AI reply"
                                        data-post-index="${index}">
                                    <i class="fas fa-robot"></i> AI Reply
                                </button>
                            ` : ''}
                            <a href="https://bsky.app/profile/${post.author.handle}/post/${post.post.uri.split('/').pop()}" 
                               target="_blank" class="btn btn-outline-primary btn-sm" title="View on Bluesky">
                                <i class="fas fa-external-link-alt"></i> View on Bluesky
                            </a>
                        </div>
                    </div>
                </div>
                <div class="card-body">
                    ${images.length > 0 ? this.createImagesSection(images, index) : ''}
                    ${post.post.text ? `<p class="card-text">${Utils.escapeHtml(post.post.text).replace(/\n/g, '<br>')}</p>` : ''}
                    
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
                        
                    </div>
                </div>
            </div>
        `;
    },

    // Create images section HTML
    createImagesSection: function(images, postIndex) {
        // Initialize carousel index to 0 for this post
        AppState.carouselIndex[postIndex] = 0;
        const first = images[0];
        const hasMultiple = images.length > 1;
        const imagesJson = encodeURIComponent(JSON.stringify(images.map(img => ({
            filename: img.filename,
            alt_text: img.alt_text || '',
            width: img.info?.width || 0,
            height: img.info?.height || 0,
            file_size: img.info?.file_size || 0
        }))));

        return `
            <div class="mt-3">
                <div class="image-container" data-images="${imagesJson}" data-post-index="${postIndex}">
                    ${hasMultiple ? `
                    <button class="carousel-btn left" type="button" aria-label="Previous image" onclick="UI.prevImage(${postIndex})">
                        <i class="fas fa-chevron-left"></i>
                    </button>` : ''}
                    <img id="post-img-${postIndex}" 
                         src="${ApiService.getImageUrl(first.filename)}" 
                         class="img-fluid rounded shadow-sm" 
                         alt="${Utils.escapeHtml(first.alt_text || '')}"
                         onclick="UI.openImageModal('${first.filename}', '${Utils.escapeHtml(first.alt_text || '')}')"
                         style="cursor: pointer;"
                         loading="lazy">
                    ${hasMultiple ? `
                    <button class="carousel-btn right" type="button" aria-label="Next image" onclick="UI.nextImage(${postIndex})">
                        <i class="fas fa-chevron-right"></i>
                    </button>` : ''}
                </div>
                <div class="d-flex justify-content-end align-items-center mt-1">
                    <small id="meta-${postIndex}" class="text-muted">
                        ${hasMultiple ? `<span id="counter-${postIndex}">1</span>/${images.length} • ` : ''}${first.info?.width || 0}×${first.info?.height || 0} • ${Utils.formatFileSize(first.info?.file_size || 0)}
                    </small>
                </div>
                <div class="smart-caption-container mt-2" id="caption-${postIndex}" style="display: none;">
                    <div class="smart-caption p-2 bg-info bg-opacity-10 rounded border-start border-info border-3">
                        <small class="text-info fw-bold">
                            <i class="fas fa-robot me-1"></i>AI Caption:
                        </small>
                        <div class="smart-caption-text mt-1"></div>
                    </div>
                </div>
            </div>
        `;
    },

    // Carousel navigation
    nextImage: function(postIndex) {
        UI._changeImage(postIndex, 1);
    },

    prevImage: function(postIndex) {
        UI._changeImage(postIndex, -1);
    },

    _changeImage: function(postIndex, delta) {
        const container = document.querySelector(`.image-container[data-post-index="${postIndex}"]`);
        if (!container) return;
        const images = JSON.parse(decodeURIComponent(container.getAttribute('data-images')));
        const total = images.length;
        if (total === 0) return;
        let idx = AppState.carouselIndex[postIndex] ?? 0;
        idx = (idx + delta + total) % total;
        AppState.carouselIndex[postIndex] = idx;

        const imgData = images[idx];
        const imgEl = document.getElementById(`post-img-${postIndex}`);
        if (!imgEl) return;
        imgEl.src = ApiService.getImageUrl(imgData.filename);
        imgEl.alt = imgData.alt_text || '';
        imgEl.setAttribute('onclick', `UI.openImageModal('${imgData.filename}', '${Utils.escapeHtml(imgData.alt_text || '')}')`);

        // No alt text visible in UI; nothing to toggle
        const counterEl = document.getElementById(`counter-${postIndex}`);
        if (counterEl) counterEl.textContent = String(idx + 1);
        const metaEl = document.getElementById(`meta-${postIndex}`);
        if (metaEl) {
            const prefix = total > 1 ? `${idx + 1}/${total} • ` : '';
            metaEl.innerHTML = `${prefix}${imgData.width || 0}×${imgData.height || 0} • ${Utils.formatFileSize(imgData.file_size || 0)}`;
        }
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
        
        // Store posts in AppState for AI Reply functionality
        AppState.posts = posts;
        
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

    // Display new posts and hide previous posts behind a collapsible section
    displayNewAndPrevious: function(newPosts, previousPosts) {
        const postsContainer = document.getElementById('posts-container');
        const emptyState = document.getElementById('empty-state');
        emptyState.style.display = 'none';

        // Build containers
        postsContainer.innerHTML = '';

        const currentSection = document.createElement('div');
        currentSection.id = 'current-posts-section';
        const currentHeader = document.createElement('div');
        currentHeader.className = 'd-flex align-items-center justify-content-between mb-2';
        currentHeader.innerHTML = `<h5 class="mb-0">Latest posts</h5><span class="text-muted small">${newPosts.length} new</span>`;
        currentSection.appendChild(currentHeader);

        // Render new posts
        newPosts.forEach((post, idx) => {
            const wrapper = document.createElement('div');
            wrapper.className = 'post-card';
            wrapper.innerHTML = this.createPostCard(post, idx);
            currentSection.appendChild(wrapper);
            setTimeout(() => wrapper.classList.add('loaded'), 50 + idx * 100);
        });

        // Previous posts collapsible
        const prevWrapper = document.createElement('div');
        prevWrapper.className = 'mt-3';
        const collapseId = 'previous-posts-collapse';
        prevWrapper.innerHTML = `
            <button class="btn btn-outline-secondary w-100" type="button" data-bs-toggle="collapse" data-bs-target="#${collapseId}" aria-expanded="false" aria-controls="${collapseId}">
                <i class="fas fa-history me-1"></i> Show previous posts (${previousPosts.length})
            </button>
            <div class="collapse mt-3" id="${collapseId}">
                <div id="previous-posts-section"></div>
            </div>
        `;

        postsContainer.appendChild(currentSection);
        postsContainer.appendChild(prevWrapper);

        const prevSection = prevWrapper.querySelector('#previous-posts-section');
        previousPosts.forEach((post, idx) => {
            const wrapper = document.createElement('div');
            wrapper.className = 'post-card';
            // Indexes for previous posts should not clash with new posts; offset by newPosts length
            wrapper.innerHTML = this.createPostCard(post, newPosts.length + idx);
            prevSection.appendChild(wrapper);
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

    // Generate AI reply for a post
    generateAiReply: async function(postIndex) {
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

        const aiReplyBtn = document.querySelector(`[data-post-index="${postIndex}"].ai-reply-btn`);
        if (!aiReplyBtn) {
            console.error('AI reply button not found for post:', postIndex);
            return;
        }

        // Show loading state
        const originalContent = aiReplyBtn.innerHTML;
        aiReplyBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Thinking...';
        aiReplyBtn.disabled = true;

        try {
            const imageFilenames = images.map(img => img.filename);
            const imageAltTexts = images.map(img => img.alt_text || '');
            const postText = post.post.text || '';
            
            // Get current theme configuration
            const themeConfig = JSON.parse(localStorage.getItem('aiThemeConfig') || '{"theme": "cycling", "tone": "enthusiastic", "style": "conversational"}');
            
            const response = await ApiService.generateAiReply(postIndex, imageFilenames, postText, imageAltTexts, themeConfig);
            
            // Show the AI reply in a modal
            this.showAiReplyModal(response.ai_reply, post, images);
            
        } catch (error) {
            console.error('Error generating AI reply:', error);
            this.showError('Failed to generate AI reply: ' + error.message);
        } finally {
            // Restore button state
            aiReplyBtn.innerHTML = originalContent;
            aiReplyBtn.disabled = false;
        }
    },

    // Show AI reply modal
    showAiReplyModal: function(aiReply, post, images) {
        // Create modal if it doesn't exist
        let modal = document.getElementById('aiReplyModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'aiReplyModal';
            modal.className = 'modal fade';
            modal.innerHTML = `
                <div class="modal-dialog modal-lg modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">
                                <i class="fas fa-robot me-2"></i>Themed AI Reply
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="mb-3">
                                <h6 class="text-muted">Original Post by @<span id="originalHandle"></span></h6>
                                <div class="small text-muted p-2 bg-light rounded">
                                    <p class="mb-2" id="originalPostText"></p>
                                    <div class="mt-2" id="imagesIncluded" style="display:none;">
                                        <small class="text-info">
                                            <i class="fas fa-images me-1"></i>
                                            <span id="imagesIncludedCount"></span> image(s) included
                                        </small>
                                    </div>
                                </div>
                            </div>
                            <div class="ai-reply-content">
                                <h6 class="text-success mb-3">
                                    <i class="fas fa-robot me-2"></i>Themed AI Reply:
                                </h6>
                                <div class="ai-reply-text p-3 bg-light rounded">
                                    <p class="mb-0" id="aiReplyText"></p>
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-warning" id="rerollBtn" onclick="UI.rerollAiReply()">
                                <i class="fas fa-dice"></i> Roll Again
                            </button>
                            <button type="button" class="btn btn-success" onclick="UI.copyAiReply()">
                                <i class="fas fa-copy"></i> Copy Reply
                            </button>
                            <a href="#" target="_blank" rel="noopener" class="btn btn-outline-primary" id="modalViewLink">
                                <i class="fas fa-external-link-alt"></i> View on Bluesky
                            </a>
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }
        
        // Update modal content for the current post
        const originalHandle = document.getElementById('originalHandle');
        if (originalHandle) originalHandle.textContent = post.author.handle;
        const originalPostText = document.getElementById('originalPostText');
        if (originalPostText) originalPostText.innerHTML = Utils.escapeHtml(post.post.text).replace(/\n/g, '<br>');
        const imagesIncluded = document.getElementById('imagesIncluded');
        const imagesIncludedCount = document.getElementById('imagesIncludedCount');
        if (imagesIncluded && imagesIncludedCount) {
            if (images && images.length > 0) {
                imagesIncluded.style.display = '';
                imagesIncludedCount.textContent = String(images.length);
            } else {
                imagesIncluded.style.display = 'none';
            }
        }
        // Set the AI reply text
        document.getElementById('aiReplyText').textContent = aiReply;
        // Store the current post index on the modal for reroll
        modal.setAttribute('data-post-index', String(AppState.posts.indexOf(post)));
        // Update View on Bluesky link
        const postUrl = `https://bsky.app/profile/${post.author.handle}/post/${post.post.uri.split('/').pop()}`;
        const viewLink = document.getElementById('modalViewLink');
        if (viewLink) viewLink.setAttribute('href', postUrl);
        
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    },

    // Reroll to generate a new AI reply for the same post
    rerollAiReply: async function() {
        const modal = document.getElementById('aiReplyModal');
        if (!modal) return;
        const postIndexAttr = modal.getAttribute('data-post-index');
        const postIndex = postIndexAttr ? parseInt(postIndexAttr, 10) : NaN;
        if (Number.isNaN(postIndex)) return;

        const post = AppState.posts[postIndex];
        if (!post) return;
        const images = post.embeds.filter(embed => embed.type === 'image');
        if (images.length === 0) return;

        const rerollBtn = document.getElementById('rerollBtn');
        const original = rerollBtn ? rerollBtn.innerHTML : '';
        if (rerollBtn) {
            rerollBtn.disabled = true;
            rerollBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Rolling...';
        }

        try {
            const imageFilenames = images.map(img => img.filename);
            const imageAltTexts = images.map(img => img.alt_text || '');
            const postText = post.post.text || '';
            const themeConfig = JSON.parse(localStorage.getItem('aiThemeConfig') || '{"theme": "cycling", "tone": "enthusiastic", "style": "conversational"}');
            const response = await ApiService.generateAiReply(postIndex, imageFilenames, postText, imageAltTexts, themeConfig);
            document.getElementById('aiReplyText').textContent = response.ai_reply;
        } catch (error) {
            console.error('Error rerolling AI reply:', error);
            UI.showError('Failed to regenerate reply: ' + error.message);
        } finally {
            if (rerollBtn) {
                rerollBtn.disabled = false;
                rerollBtn.innerHTML = original;
            }
        }
    },

    // Copy AI reply to clipboard
    copyAiReply: function() {
        const replyText = document.getElementById('aiReplyText').textContent;
        navigator.clipboard.writeText(replyText).then(() => {
            // Show success feedback
            const copyBtn = document.querySelector('#aiReplyModal .btn-success');
            const originalText = copyBtn.innerHTML;
            copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
            
            setTimeout(() => {
                copyBtn.innerHTML = originalText;
            }, 2000);
        }).catch(err => {
            console.error('Failed to copy text: ', err);
            this.showError('Failed to copy response to clipboard');
        });
    },

};

// Main app controller
const App = {
    // Initialize the app
    init: function() {
        console.log('App initializing...');
        // Ensure currentCount aligns with the UI default selection (prevents stale localStorage overriding defaults)
        const checked = document.querySelector('input[name="postCount"]:checked');
        if (checked) {
            const uiCount = parseInt(checked.value);
            if (!Number.isNaN(uiCount)) {
                AppState.currentCount = uiCount;
                localStorage.setItem('postCount', String(AppState.currentCount));
            }
        }
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

        // Fetch more button
        const fetchMoreBtn = document.getElementById('fetch-more-btn');
        if (fetchMoreBtn) {
            fetchMoreBtn.addEventListener('click', () => {
                const newCount = Math.min(AppState.currentCount + 9, 18);
                if (newCount !== AppState.currentCount) {
                    // Mark that we are fetching more and store previously shown posts
                    AppState.wasFetchMore = true;
                    AppState.previousPosts = Array.isArray(AppState.posts) ? AppState.posts.slice() : [];
                    AppState.currentCount = newCount;
                    localStorage.setItem('postCount', String(AppState.currentCount));
                    this.syncPostCountRadios();
                    this.updateFetchMoreButton();
                    this.loadPostsWithProgress();
                }
            });
        }

        // Post count radio buttons
        document.querySelectorAll('input[name="postCount"]').forEach(radio => {
            // Initialize checked state from saved value
            if (parseInt(radio.value) === AppState.currentCount) {
                radio.checked = true;
            }

            radio.addEventListener('change', (e) => {
                if (e.target.checked) {
                    AppState.currentCount = parseInt(e.target.value);
                    localStorage.setItem('postCount', String(AppState.currentCount));
                    this.updateFetchMoreButton();
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

        // Ensure controls reflect initial state
        this.updateFetchMoreButton();
    },

    // Keep the radio group in sync when count changes programmatically
    syncPostCountRadios: function() {
        document.querySelectorAll('input[name="postCount"]').forEach(radio => {
            radio.checked = parseInt(radio.value) === AppState.currentCount;
        });
    },

    // Enable/disable the fetch more button based on current count
    updateFetchMoreButton: function() {
        const fetchMoreBtn = document.getElementById('fetch-more-btn');
        if (!fetchMoreBtn) return;
        const atMax = AppState.currentCount >= 18;
        fetchMoreBtn.disabled = atMax;
        fetchMoreBtn.textContent = atMax ? 'Max reached' : 'Fetch more';
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
                                if (AppState.wasFetchMore && AppState.previousPosts.length > 0) {
                                    // Combine new + previous for state, render with collapsible
                                    const combined = data.posts.concat(AppState.previousPosts);
                                    AppState.posts = combined;
                                    UI.displayNewAndPrevious(data.posts, AppState.previousPosts);
                                } else {
                                    UI.displayPostsProgressively(data.posts);
                                    AppState.posts = data.posts;
                                }
                                // Reset fetch-more state
                                AppState.wasFetchMore = false;
                                AppState.previousPosts = [];
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
