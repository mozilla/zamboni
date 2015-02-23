(function() {
    if (z.capabilities.filesystem) {
        document.body.classList.add('filesystem');
    }

    require('install');
})();
