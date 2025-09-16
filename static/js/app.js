// Bluesky Timeline App JavaScript

// Global app state
const AppState = {
    posts: [],
    isLoading: false,
    currentCount: parseInt(localStorage.getItem('postCount') || '9'),
    maxPerUser: parseInt(localStorage.getItem('maxPerUser') || '1'),
    lastRefresh: null,
    carouselIndex: {},
    previousPosts: [],
    wasFetchMore: false,
    sessionId: localStorage.getItem('sessionId') || generateSessionId()
};

// Generate a unique session ID
function generateSessionId() {
    const sessionId = 'session_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
    localStorage.setItem('sessionId', sessionId);
    return sessionId;
}

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
    },

    // Load image with retry logic
    loadImageWithRetry: function(imgElement, src, maxRetries = 3, retryDelay = 1000) {
        return new Promise((resolve, reject) => {
            let retryCount = 0;
            
            const attemptLoad = () => {
                const img = new Image();
                
                img.onload = () => {
                    imgElement.src = src;
                    imgElement.classList.remove('loading', 'error');
                    imgElement.classList.add('loaded');
                    resolve(imgElement);
                };
                
                img.onerror = () => {
                    retryCount++;
                    if (retryCount < maxRetries) {
                        console.warn(`Image load failed, retrying... (${retryCount}/${maxRetries})`);
                        imgElement.classList.add('retrying');
                        setTimeout(attemptLoad, retryDelay * retryCount); // Exponential backoff
                    } else {
                        console.error(`Image load failed after ${maxRetries} attempts:`, src);
                        imgElement.classList.remove('loading', 'retrying');
                        imgElement.classList.add('error');
                        reject(new Error(`Failed to load image after ${maxRetries} attempts`));
                    }
                };
                
                img.src = src;
            };
            
            imgElement.classList.add('loading');
            attemptLoad();
        });
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

    async getPosts(count = 5, fetchMore = false, maxPerUser = 1, sessionId = null) {
        const sessionParam = sessionId ? `&session_id=${sessionId}` : '';
        return this.request(`/api/posts?count=${count}&fetch_more=${fetchMore}&max_per_user=${maxPerUser}${sessionParam}`);
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
    },

    async likePost(postUri) {
        return this.request('/api/like', {
            method: 'POST',
            body: JSON.stringify({
                post_uri: postUri
            })
        });
    },

    async unlikePost(postUri) {
        return this.request('/api/unlike', {
            method: 'POST',
            body: JSON.stringify({
                post_uri: postUri
            })
        });
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
            // Create a more informative progress message
            let progressDetails = '';
            if (postsFound > 0) {
                progressDetails = `Found ${postsFound} posts with images • Checked ${postsChecked} total posts • Batch ${currentBatch}`;
            } else if (postsChecked > 0) {
                progressDetails = `Checked ${postsChecked} total posts • No new posts with images found • Batch ${currentBatch}`;
            } else if (currentBatch > 0) {
                progressDetails = `Processed ${currentBatch} batches • No new posts with images found`;
            } else {
                progressDetails = `Searching for posts with images...`;
            }
            
            progressText.innerHTML = `
                <h4 class="text-primary mb-2">${message}</h4>
                <p class="text-muted mb-2">${progressDetails}</p>
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

    // Show success message
    showSuccess: function(message) {
        const successAlert = document.getElementById('success-alert');
        if (successAlert) {
            const successMessage = successAlert.querySelector('#success-message') || successAlert;
            successMessage.textContent = message;
            successAlert.style.display = 'block';
            setTimeout(() => {
                successAlert.style.display = 'none';
            }, 3000);
        } else {
            console.log('Success:', message);
        }
    },

    // Show warning message
    showWarning: function(message) {
        const warningAlert = document.getElementById('warning-alert');
        if (warningAlert) {
            const warningMessage = warningAlert.querySelector('#warning-message') || warningAlert;
            warningMessage.textContent = message;
            warningAlert.style.display = 'block';
            setTimeout(() => {
                warningAlert.style.display = 'none';
            }, 3000);
        } else {
            console.warn('Warning:', message);
        }
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
        
        // Check if this post is already liked (we'll implement this later)
        const isLiked = post.post.is_liked || false;
        const likeButtonClass = isLiked ? 'like-button liked' : 'like-button';
        
        return `
            <div class="card mb-4" data-post-index="${index}">
                <div class="card-header">
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
                </div>
                ${post.post.text ? `<div class="card-text">${Utils.escapeHtml(post.post.text).replace(/\n/g, '<br>')}</div>` : ''}
                <div class="engagement-metrics">
                    <div class="d-flex justify-content-between align-items-center">
                        <div class="engagement-stats">
                            <span class="engagement-item me-3" title="Replies">
                                <i class="fas fa-reply"></i> ${post.post.reply_count}
                            </span>
                            <span class="engagement-item me-3" title="Reposts">
                                <i class="fas fa-retweet"></i> ${post.post.repost_count}
                            </span>
                            <span class="${likeButtonClass}" title="Likes" data-post-uri="${post.post.uri}" data-post-index="${index}">
                                <i class="fas fa-heart"></i> <span class="like-count">${post.post.like_count}</span>
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
                         class="img-fluid rounded shadow-sm clickable-image loading" 
                         alt="${Utils.escapeHtml(first.alt_text || '')}"
                         data-filename="${first.filename}"
                         data-alt-text="${Utils.escapeHtml(first.alt_text || '')}"
                         data-src="${ApiService.getImageUrl(first.filename)}"
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
        
        const newSrc = ApiService.getImageUrl(imgData.filename);
        imgEl.alt = imgData.alt_text || '';
        imgEl.setAttribute('data-filename', imgData.filename);
        imgEl.setAttribute('data-alt-text', Utils.escapeHtml(imgData.alt_text || ''));
        imgEl.setAttribute('data-src', newSrc);
        
        // Load image with retry logic
        Utils.loadImageWithRetry(imgEl, newSrc).catch(error => {
            console.error('Failed to load image in carousel:', error);
        });

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
        
        // Add direct click event listeners to like buttons
        const likeButtons = postsContainer.querySelectorAll('.like-button');
        likeButtons.forEach(likeButton => {
            likeButton.addEventListener('click', (e) => {
                UI.handleLikeClick(e);
            });
        });
        
        // Initialize image loading for all images
        this.initializeImageLoading();
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
                
                // Initialize image loading for this post
                this.initializeImageLoadingForPost(postElement);
                
                // Add click event listener to like button for this post
                const likeButton = postElement.querySelector('.like-button');
                if (likeButton) {
                    likeButton.addEventListener('click', (e) => {
                        UI.handleLikeClick(e);
                    });
                }
                
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

        // Clear container and maintain grid structure
        postsContainer.innerHTML = '';

        // Add a header for new posts (this will span the full grid width)
        const headerDiv = document.createElement('div');
        headerDiv.className = 'grid-header';
        headerDiv.style.gridColumn = '1 / -1'; // Span all columns
        headerDiv.style.marginBottom = '1rem';
        headerDiv.innerHTML = `
            <div class="d-flex align-items-center justify-content-between">
                <h5 class="mb-0">Latest posts</h5>
                <span class="text-muted small">${newPosts.length} new</span>
            </div>
        `;
        postsContainer.appendChild(headerDiv);

        // Render new posts in grid
        newPosts.forEach((post, idx) => {
            const wrapper = document.createElement('div');
            wrapper.className = 'post-card';
            wrapper.innerHTML = this.createPostCard(post, idx);
            postsContainer.appendChild(wrapper);
            
            // Add click event listener to like button for this post
            const likeButton = wrapper.querySelector('.like-button');
            if (likeButton) {
                likeButton.addEventListener('click', (e) => {
                    UI.handleLikeClick(e);
                });
            }
            
            setTimeout(() => wrapper.classList.add('loaded'), 50 + idx * 100);
        });

        // Add a collapsible section for previous posts
        const prevHeaderDiv = document.createElement('div');
        prevHeaderDiv.className = 'grid-header';
        prevHeaderDiv.style.gridColumn = '1 / -1'; // Span all columns
        prevHeaderDiv.style.marginTop = '2rem';
        prevHeaderDiv.style.marginBottom = '1rem';
        
        const collapseId = 'previous-posts-collapse';
        prevHeaderDiv.innerHTML = `
            <button class="btn btn-outline-secondary w-100" type="button" data-bs-toggle="collapse" data-bs-target="#${collapseId}" aria-expanded="false" aria-controls="${collapseId}">
                <i class="fas fa-history me-1"></i> Show previous posts (${previousPosts.length})
            </button>
        `;
        postsContainer.appendChild(prevHeaderDiv);

        // Add collapsible container for previous posts
        const prevContainerDiv = document.createElement('div');
        prevContainerDiv.className = 'collapse';
        prevContainerDiv.id = collapseId;
        prevContainerDiv.style.gridColumn = '1 / -1'; // Span all columns
        
        const prevPostsGrid = document.createElement('div');
        prevPostsGrid.style.display = 'grid';
        prevPostsGrid.style.gridTemplateColumns = 'repeat(3, 1fr)';
        prevPostsGrid.style.gap = '1.5rem';
        prevPostsGrid.style.maxWidth = '1200px';
        prevPostsGrid.style.margin = '0 auto';
        
        prevContainerDiv.appendChild(prevPostsGrid);
        postsContainer.appendChild(prevContainerDiv);

        // Render previous posts in the collapsible grid
        previousPosts.forEach((post, idx) => {
            const wrapper = document.createElement('div');
            wrapper.className = 'post-card';
            // Indexes for previous posts should not clash with new posts; offset by newPosts length
            wrapper.innerHTML = this.createPostCard(post, newPosts.length + idx);
            prevPostsGrid.appendChild(wrapper);
            
            // Add click event listener to like button for this post
            const likeButton = wrapper.querySelector('.like-button');
            if (likeButton) {
                likeButton.addEventListener('click', (e) => {
                    UI.handleLikeClick(e);
                });
            }
        });
    },

    // Initialize image loading for all images
    initializeImageLoading: function() {
        const images = document.querySelectorAll('.clickable-image[data-src]');
        images.forEach(img => {
            const src = img.getAttribute('data-src');
            if (src) {
                Utils.loadImageWithRetry(img, src).catch(error => {
                    console.error('Failed to load image:', error);
                });
            }
        });
    },

    // Initialize image loading for a specific post element
    initializeImageLoadingForPost: function(postElement) {
        const images = postElement.querySelectorAll('.clickable-image[data-src]');
        images.forEach(img => {
            const src = img.getAttribute('data-src');
            if (src) {
                Utils.loadImageWithRetry(img, src).catch(error => {
                    console.error('Failed to load image:', error);
                });
            }
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

    // Handle like button click
    handleLikeClick: function(event) {
        // Handle both real events and custom objects
        if (event && typeof event.preventDefault === 'function') {
            event.preventDefault();
            event.stopPropagation();
        }
        
        const likeButton = event.currentTarget;
        const postUri = likeButton.getAttribute('data-post-uri');
        const postIndex = parseInt(likeButton.getAttribute('data-post-index'));
        
        if (!postUri || isNaN(postIndex)) {
            console.error('Invalid like button data:', { postUri, postIndex });
            return;
        }

        // Check if already liked
        const isLiked = likeButton.classList.contains('liked');
        
        // Set loading state
        likeButton.classList.add('loading');
        likeButton.style.pointerEvents = 'none';

        // Call appropriate API method
        const apiCall = isLiked ? ApiService.unlikePost(postUri) : ApiService.likePost(postUri);
        
        apiCall.then(response => {
            if (response.success) {
                // Update UI state
                const likeCountSpan = likeButton.querySelector('.like-count');
                const currentCount = parseInt(likeCountSpan.textContent) || 0;
                const newCount = isLiked ? Math.max(0, currentCount - 1) : currentCount + 1;
                
                likeCountSpan.textContent = newCount;
                
                // Update like state
                if (isLiked) {
                    likeButton.classList.remove('liked');
                } else {
                    likeButton.classList.add('liked');
                }
                
                // Update the post data in AppState
                if (AppState.posts[postIndex]) {
                    AppState.posts[postIndex].post.like_count = newCount;
                    AppState.posts[postIndex].post.is_liked = !isLiked;
                }
                
                // Success feedback removed - users can see heart fill/unfill and count change
            } else {
                console.error('Like action failed:', response.error);
                
                // Handle specific error cases
                if (response.already_liked) {
                    this.showWarning('Post is already liked');
                    // Update UI to reflect the actual state
                    likeButton.classList.add('liked');
                    if (AppState.posts[postIndex]) {
                        AppState.posts[postIndex].post.is_liked = true;
                    }
                } else if (response.not_liked) {
                    this.showWarning('Post is not liked');
                    // Update UI to reflect the actual state
                    likeButton.classList.remove('liked');
                    if (AppState.posts[postIndex]) {
                        AppState.posts[postIndex].post.is_liked = false;
                    }
                } else {
                    this.showError('Failed to ' + (isLiked ? 'unlike' : 'like') + ' post: ' + (response.error || 'Unknown error'));
                }
            }
        }).catch(error => {
            console.error('Error with like action:', error);
            this.showError('Error ' + (isLiked ? 'unliking' : 'liking') + ' post: ' + error.message);
        }).finally(() => {
            // Remove loading state
            likeButton.classList.remove('loading');
            likeButton.style.pointerEvents = 'auto';
        });
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
        
        // Ensure maxPerUser aligns with the UI default selection
        const checkedMaxPerUser = document.querySelector('input[name="maxPerUser"]:checked');
        if (checkedMaxPerUser) {
            const uiMaxPerUser = parseInt(checkedMaxPerUser.value);
            if (!Number.isNaN(uiMaxPerUser)) {
                AppState.maxPerUser = uiMaxPerUser;
                localStorage.setItem('maxPerUser', String(AppState.maxPerUser));
            }
        }
        this.setupEventListeners();
        // Load user info, posts, and check status
        this.loadUserInfo();
        // Check status first, then load posts
        this.checkStatus().then(() => {
            // Add a small delay to ensure DOM is fully ready before loading posts
            setTimeout(() => {
                console.log('Starting to load posts after status check...');
                this.loadPostsWithProgress().catch(error => {
                    console.error('Failed to load posts on init:', error);
                });
            }, 100);
        }).catch(error => {
            console.error('Status check failed, trying to load posts anyway:', error);
            // Try to load posts even if status check fails
            setTimeout(() => {
                this.loadPostsWithProgress().catch(loadError => {
                    console.error('Failed to load posts after status check failure:', loadError);
                });
            }, 100);
        });
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
                // For fetch more, we want to get NEW posts and append them
                // We don't change the count, we just fetch more posts
                AppState.wasFetchMore = true;
                AppState.previousPosts = Array.isArray(AppState.posts) ? AppState.posts.slice() : [];
                this.loadPostsWithProgress(true); // Pass true for fetchMore
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

        // Max per user radio buttons
        document.querySelectorAll('input[name="maxPerUser"]').forEach(radio => {
            // Initialize checked state from saved value
            if (parseInt(radio.value) === AppState.maxPerUser) {
                radio.checked = true;
            }

            radio.addEventListener('change', (e) => {
                if (e.target.checked) {
                    AppState.maxPerUser = parseInt(e.target.value);
                    localStorage.setItem('maxPerUser', String(AppState.maxPerUser));
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

        // Image click event delegation for better reliability
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('clickable-image')) {
                if (e.target.classList.contains('loaded')) {
                    // Open modal for loaded images
                    e.preventDefault();
                    e.stopPropagation();
                    const filename = e.target.getAttribute('data-filename');
                    const altText = e.target.getAttribute('data-alt-text');
                    if (filename) {
                        UI.openImageModal(filename, altText || '');
                    }
                } else if (e.target.classList.contains('error')) {
                    // Retry loading for failed images
                    e.preventDefault();
                    e.stopPropagation();
                    const src = e.target.getAttribute('data-src');
                    if (src) {
                        e.target.classList.remove('error');
                        e.target.classList.add('loading');
                        Utils.loadImageWithRetry(e.target, src).catch(error => {
                            console.error('Retry failed:', error);
                        });
                    }
                }
            } else if (e.target.closest('.like-button')) {
                // Handle like button clicks
                const likeButton = e.target.closest('.like-button');
                // Create a synthetic event object with the correct currentTarget
                const syntheticEvent = {
                    currentTarget: likeButton,
                    preventDefault: () => e.preventDefault(),
                    stopPropagation: () => e.stopPropagation()
                };
                UI.handleLikeClick(syntheticEvent);
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
            console.log('Status check result:', data);
            return data;
        } catch (error) {
            console.error('Status check failed:', error);
            UI.updateStatus(false);
            throw error;
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
            const data = await ApiService.getPosts(AppState.currentCount, false, AppState.maxPerUser, AppState.sessionId);
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
    async loadPostsWithProgress(fetchMore = false) {
        if (AppState.isLoading) {
            console.log('Already loading posts, skipping...');
            return;
        }

        console.log('Loading posts with progress...', { count: AppState.currentCount, fetchMore, maxPerUser: AppState.maxPerUser, sessionId: AppState.sessionId });
        UI.showLoading();
        
        try {
            const streamUrl = `/api/posts/stream?count=${AppState.currentCount}&max_per_user=${AppState.maxPerUser}&fetch_more=${fetchMore}&session_id=${AppState.sessionId}`;
            console.log('Streaming URL:', streamUrl);
            const eventSource = new EventSource(streamUrl);
            
            // Add timeout to detect if EventSource fails to connect (increased to 30 seconds)
            const connectionTimeout = setTimeout(() => {
                console.error('EventSource connection timeout after 30 seconds');
                eventSource.close();
                UI.showError('Connection timeout - please check your network and try again');
                UI.hideLoading();
            }, 30000);
            
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
                            
                        case 'keepalive':
                            console.log('Keep-alive received:', data.message);
                            // Reset timeout on keep-alive to prevent connection timeout
                            clearTimeout(connectionTimeout);
                            const newTimeout = setTimeout(() => {
                                console.error('EventSource connection timeout after 30 seconds');
                                eventSource.close();
                                UI.showError('Connection timeout - please check your network and try again');
                                UI.hideLoading();
                            }, 30000);
                            // Update the timeout reference
                            connectionTimeout = newTimeout;
                            break;
                            
                        case 'complete':
                            console.log('Posts loaded:', data);
                            clearTimeout(connectionTimeout); // Clear the timeout since we got a response
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
                            clearTimeout(connectionTimeout); // Clear the timeout since we got an error
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
                clearTimeout(connectionTimeout); // Clear the timeout since we got an error
                UI.showError('Connection lost while fetching posts');
                eventSource.close();
                UI.hideLoading();
            };
            
        } catch (error) {
            console.error('Error setting up stream:', error);
            // Fallback to non-streaming API if EventSource fails
            console.log('Falling back to non-streaming API...');
            this.loadPosts().catch(fallbackError => {
                console.error('Fallback also failed:', fallbackError);
                UI.showError('Failed to load posts: ' + fallbackError.message);
            });
        }
    }
};

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, initializing app...');
    // Add a small delay to ensure all DOM elements are fully rendered
    setTimeout(() => {
        App.init();
    }, 50);
});

// Fallback initialization in case DOMContentLoaded already fired
if (document.readyState === 'loading') {
    // DOM is still loading, wait for DOMContentLoaded
} else {
    // DOM is already loaded, initialize immediately
    console.log('DOM already loaded, initializing app immediately...');
    setTimeout(() => {
        App.init();
    }, 50);
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
