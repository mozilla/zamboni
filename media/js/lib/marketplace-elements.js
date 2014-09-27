define('marketplace-elements', [], function () {
    // Abstract element with attribute -> class mappings.
    var MktHTMLElement = function () {};
    MktHTMLElement.prototype = Object.create(HTMLElement.prototype, {
        attributeChangedCallback: {
            value: function (name, previousValue, value) {
                // Handle setting classes based on attributeClasses.
                if (this.attributeClasses.hasOwnProperty(name)) {
                    var className = this.attributeClasses[name];
                    if (value === null) {
                        this.classList.remove(className);
                    } else {
                        this.classList.add(className);
                    }
                }
            },
        },
        attributeClasses: {
            value: {},
        },
        createdCallback: {
            value: function () {
                var self = this;
                Object.keys(this.attributeClasses).forEach(function (attr) {
                    var className = self.attributeClasses[attr];
                    if (self.hasAttribute(attr) && className) {
                        self.classList.add(className);
                    }
                    self.__defineGetter__(attr, function () {
                        // Treat `foo=""` as `foo=true`.
                        return self.getAttribute(attr) ||
                            self.hasAttribute(attr);
                    });
                    self.__defineSetter__(attr, function (value) {
                        if (value === null || value === false) {
                            self.removeAttribute(attr);
                        } else {
                            self.setAttribute(attr, value || true);
                        }
                    });
                });
            },
        },
    });

    var MktBanner = document.registerElement('mkt-banner', {
        prototype: Object.create(MktHTMLElement.prototype, {
            attributeClasses: {
                value: {
                    success: 'mkt-banner-success',
                    dismiss: null,
                },
            },
            createdCallback: {
                value: function () {
                    MktHTMLElement.prototype.createdCallback.call(this);
                    this.classList.add('mkt-banner');

                    // This is a Firefox banner if it isn't a success banner.
                    if (!this.success) {
                        this.classList.add('mkt-banner-firefox');
                    }

                    if (this.rememberDismissal && this.dismissed) {
                        this.dismissBanner();
                    }

                    // Format the initial HTML.
                    this.html(this.innerHTML);
                },
            },
            html: {
                value: function (html) {
                    var self = this;

                    var content = document.createElement('div');
                    content.classList.add('mkt-banner-content');
                    content.innerHTML = html;

                    if (!this.undismissable) {
                        var closeButton = document.createElement('a');
                        closeButton.classList.add('close');
                        closeButton.href = '#';
                        closeButton.textContent = gettext('Close');
                        closeButton.title = gettext('Close');
                        closeButton.addEventListener('click', function (e) {
                            e.preventDefault();
                            self.dismissBanner();
                        });
                        content.appendChild(closeButton);
                    }

                    this.innerHTML = '';
                    this.appendChild(content);
                },
            },
            dismissed: {
                get: function () {
                    return this.storage.getItem(this.storageKey);
                },
            },
            dismissBanner: {
                value: function () {
                    if (this.rememberDismissal) {
                        this.storage.setItem(this.storageKey, true);
                    }
                    this.parentNode.removeChild(this);
                },
            },
            rememberDismissal: {
                get: function () {
                    return this.dismiss === 'remember';
                },
            },
            storage: {
                get: function () {
                    return require('storage');
                },
            },
            storageKey: {
                get: function () {
                    return 'hide_' + this.id.replace(/-/g, '_');
                },
            },
            undismissable: {
                get: function () {
                    return this.dismiss === 'off';
                },
            },
        }),
    });

    var MktLogin = document.registerElement('mkt-login', {
        prototype: Object.create(MktHTMLElement.prototype, {
            createdCallback: {
                value: function () {
                    if (this.isLink) {
                        var link = document.createElement('a');
                        link.href = '#';
                        link.classList.add('persona');
                        link.textContent = this.textContent;
                        this.innerHTML = '';
                        this.appendChild(link);
                    }
                },
            },
            isLink: {
                get: function () {
                    return this.hasAttribute('link');
                },
            },
        }),
    });
});
