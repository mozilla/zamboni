define('storage', [], function() {
    function Storage() {
        function _prefix(storageKey) {
            // We used to have storage versioning here (bug 1144437).
            return '0::' + storageKey;
        }

        this.setItem = function (key, value) {
            return localStorage.setItem(_prefix(key), JSON.stringify(value));
        };

        this.getItem = function (key) {
            value = localStorage.getItem(_prefix(key));
            try {
                return JSON.parse(value);
            } catch(e) {
                return value;
            }
        };

        this.removeItem = function (key) {
            return localStorage.removeItem(_prefix(key));
        };
    }

    return new Storage();
});
