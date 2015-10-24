define('login', ['notification', 'storage'], function(notification, storage) {
    var requestedLogin = false;
    var readyForReload = false;

    z.doc.bind('login', function(skipDialog) {
        if (readyForReload) {
            window.location.reload();
            return;
        }
        if (skipDialog) {
            startLogin();
        } else {
            $('.overlay.login').addClass('show');
        }
    }).on('click', '.browserid', loginHandler)
      .on('click', '.persona', loginHandler);

    function loginHandler(e) {
        if (readyForReload) {
            window.location.reload();
            return;
        }

        var $this = $(this);
        $this.addClass('loading-submit');
        z.doc.on('logincancel', function() {
            $this.removeClass('loading-submit').blur();
        });
        if (z.body.data('persona-url')) {
            startLogin();
        } else {
            startFxALogin({
                action: $this.hasClass('register') ?  'signup' : 'signin',
            });
        }
        e.preventDefault();
    }

    function getCenteredCoordinates (width, height) {
        var x = window.screenX + Math.max(0, Math.floor((window.innerWidth - width) / 2));
        var y = window.screenY + Math.max(0, Math.floor((window.innerHeight - height) / 2));
        return [x, y];
    }

    function startFxALogin(options) {
        options = options || {};
        var w = 320;
        var h = 600;
        var i = getCenteredCoordinates(w, h);
        requestedLogin = true;

        var fxa_auth_url = z.body.data('fxa-login-url');
        if (options.action) {
            fxa_auth_url += '&action=' + options.action;
        }
        var popup = window.open(fxa_auth_url, 'fxa',
            'scrollbars=yes,width=' + w + ',height=' + h +
            ',left=' + i[0] + ',top=' + i[1]);

        window.addEventListener("message", function (msg) {
            if (!msg.data || !msg.data.auth_code) {
                return;
            }
            var data = {
                'auth_response': msg.data.auth_code,
                'state': z.body.data('fxa-state')
            };
            $.ajax({
                type: 'POST',
                url: z.body.data('fxa-auth-url'),
                contentType: 'application/json',
                data: JSON.stringify(data),
                dataType: 'json'}).done(finishLogin);

            // Close popup on receipt of message.
            if (popup) {
                popup.close();
            }
        });
    }

    function startLogin() {
        requestedLogin = true;
        var forcedIssuer = document.body.dataset.personaUnverifiedIssuer;
        var mediaUrl = document.body.dataset.mediaUrl;
        if (mediaUrl.indexOf('https:') === -1) {
            mediaUrl = 'https://marketplace.cdn.mozilla.net/media';
        }
        var params = {
            siteLogo: mediaUrl + '/img/mkt/logos/128.png?siteLogo',
            termsOfService: '/terms-of-use',
            privacyPolicy: '/privacy-policy',
            oncancel: function() {
                z.doc.trigger('logincancel');
            }
        };
        if (forcedIssuer) {
            console.log('Login is forcing issuer:', forcedIssuer);
            params.experimental_forceIssuer = forcedIssuer;
        }
        navigator.id.request(params);
    }

    z.body.on('click', '.logout', function() {
        // NOTE: Real logout operations happen on the action of the Logout
        // link/button. This just tells Persona to clean up its data.
        if (navigator.id) {
            navigator.id.logout();
        }
        clearToken();

    });
    function gotVerifiedEmail(assertion) {
        if (assertion) {
            var data = {assertion: assertion};
            // This login code only runs on desktop so we are disabling
            // mobile-like login behaviors such as unverified emails.
            // See Fireplace for mobile logic.
            data.is_mobile = 0;

            $.post(z.body.data('login-url'), data, 'json')
             .success(finishLogin)
             .error(function(jqXHR, textStatus, error) {
                var err = jqXHR.responseText;
                if (!err) {
                    err = gettext("Persona login failed. Maybe you don't have an account under that email address?") + " " + textStatus + " " + error;
                }
                // Catch-all for XHR errors otherwise we'll trigger 'notify'
                // with its message as one of the error templates.
                if (jqXHR.status != 200) {
                    err = gettext('Persona login failed. A server error was encountered.');
                }
                z.page.trigger('notify', {msg: err});
             });
        } else {
            $('.loading-submit').removeClass('loading-submit');
        }
    }

    function finishLogin(data) {
        setToken(data);

        var to = z.getVars().to;
        if (to && to[0] == '/') {
            // Browsers may helpfully add "http:" to URIs that begin with double
            // slashes. This converts instances of double slashes to single to
            // avoid other helpfullness. It's a bit of extra paranoia.
            to = decodeURIComponent(to.replace(/\/*/, '/'));
            // Convert a local URI to a fully qualified local URL.
            window.location = window.location.protocol + '//'  +
                window.location.host + to;
        } else {
            console.log('finished login');
            if (requestedLogin) {
                window.location.reload();
            } else {
                console.log('User logged in; ready for reload');
                readyForReload = true;
            }
        }
    }

    function init_native_fxa() {
        var user = z.body.data('user');
        var email = user ? user.email : '';
        console.log('detected user', email);
        var packaged_origin = "app://packaged." + window.location.host;
        if (window.location.host === "marketplace.firefox.com") {
            packaged_origin = "app://marketplace.firefox.com";
        }
        var isFirefoxOS = (navigator.mozApps && navigator.mozApps.installPackage &&
            navigator.userAgent.indexOf('Android') === -1 &&
            (navigator.userAgent.indexOf('Mobile') !== -1 ||
             navigator.userAgent.indexOf('Tablet') !== -1));
        var hasFxA = isFirefoxOS && navigator.userAgent.match(/rv:(\d{2})/)[1] >= 34;
        var isYulelogFxA = window.top !== window.self && hasFxA;
        if (isYulelogFxA) {
            window.addEventListener('message', function (msg) {
                if (!msg.data || !msg.data.type || msg.origin !== packaged_origin) {
                    return;
                }
                console.log("fxa message " + JSON.stringify(msg.data));
                if (msg.data.type === 'fxa-logout') {
                    clearToken();
                    window.location = '/';
                }
            });
        } else if (hasFxA) {
            navigator.mozId.watch({
                loggedInUser: email,
                onlogin: function(assertion) {
                    if (!email) {
                        gotVerifiedEmail(assertion);
                    }
                },
                onlogout: function() {
                    clearToken();
                    }
            });
        }
    }

    function setToken(data) {
        storage.setItem('user', data.token);
        storage.setItem('settings', data.settings);
        storage.setItem('permissions', data.permissions);
        storage.setItem('user_apps', data.apps);
    }

    function clearToken() {
        storage.removeItem('user');
        storage.removeItem('settings');
        storage.removeItem('permissions');
        storage.removeItem('user_apps');
    }

    function userToken() {
        return storage.getItem('user');
    }

    init_native_fxa();

    return {
        userToken: userToken
    };
});
