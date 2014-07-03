// CSRF Tokens
// Hijack the AJAX requests, and insert a CSRF token as a header.
$(document).ajaxSend(function(event, xhr, ajaxSettings) {
    // Block anything that starts with '<text>://', '://' or '//'.
    if (isLocalUrl(ajaxSettings.url)) {
        var $meta = $('meta[name=csrf]');
        var csrf;
        if (!z.anonymous && $meta.length) {
            csrf = $meta.attr('content');
        } else {
            csrf = $("input[name='csrfmiddlewaretoken']").val();
        }
        if (csrf) {
            xhr.setRequestHeader('X-CSRFToken', csrf);
        }
    }
});
