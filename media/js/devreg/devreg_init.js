// Do this last- initialize the marketplace!

define('developers', ['login', 'marketplace-elements', 'notification', 'tracking'], function() {
    $('.mkt-cloak').removeClass('mkt-cloak');
});
require('developers');
require('test-install');
require('iarc-ratings');
require('tracking_app_submit');
