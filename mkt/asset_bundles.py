# A list of our CSS and JS assets for jingo-minify.

CSS = {
    'mkt/admin': (
        'css/zamboni/zamboni.css',
        'css/zamboni/mkt-admin.css',
        'css/zamboni/admin-django.css',
    ),
    'mkt/devreg': (
        # Contains reset, clearfix, etc.
        'css/devreg/base.css',

        # Base styles (body, breadcrumbs, islands, columns).
        'css/devreg/base.styl',
        'css/devreg/breadcrumbs.styl',

        # Typographical styles (font treatments, headings).
        'css/devreg/typography.styl',

        # Header (aux-nav, masthead, site-nav).
        'css/devreg/desktop-account-links.styl',
        'css/devreg/header.styl',

        # Item rows (used on Dashboard).
        'css/devreg/listing.styl',
        'css/devreg/legacy-paginator.styl',

        # Buttons (used for paginator, "Edit" buttons, Refunds page).
        'css/devreg/buttons.styl',

        # Forms (used for tables on "Manage ..." pages).
        'css/devreg/forms.styl',

        # Popups, Modals, Tooltips.
        'css/devreg/notification.styl',
        'css/devreg/overlay.styl',
        'css/devreg/popups.styl',
        'css/devreg/device.styl',
        'css/devreg/tooltips.styl',

        # L10n menu ("Localize for ...").
        'css/devreg/l10n.styl',

        # Tables.
        'css/devreg/data-grid.styl',

        # "Manage ..." pages.
        'css/devreg/manage.styl',
        'css/devreg/prose.styl',
        'css/devreg/authors.styl',
        'css/devreg/in-app-config.styl',
        'css/devreg/payments.styl',
        'css/devreg/transactions.styl',
        'css/devreg/status.styl',
        'css/devreg/content_ratings.styl',

        # Image Uploads (used for "Edit Listing" Images and Submission).
        'css/devreg/media.styl',
        'css/devreg/invisible-upload.styl',

        # Submission.
        'css/devreg/submit-progress.styl',
        'css/devreg/submit-terms.styl',
        'css/devreg/submit-manifest.styl',
        'css/devreg/submit-details.styl',
        'css/devreg/validation.styl',
        'css/devreg/submit.styl',
        'css/devreg/tabs.styl',

        # Developer Log In / Registration.
        'css/devreg/login.styl',

        # Footer.
        'css/devreg/footer.styl',

        # Marketplace elements.
        'css/lib/marketplace-elements.css',
    ),
    'mkt/reviewers': (
        'css/zamboni/editors.styl',
        'css/devreg/consumer-buttons.styl',
        'css/devreg/content_ratings.styl',
        'css/devreg/data-grid.styl',
        'css/devreg/manifest.styl',
        'css/devreg/reviewers.styl',
        'css/devreg/reviewers-header.styl',
        'css/devreg/reviewers-mobile.styl',
        'css/devreg/legacy-paginator.styl',
        'css/devreg/files.styl',
    ),
    'mkt/ecosystem': (
        'css/devreg/reset.styl',
        'css/devreg/consumer-typography.styl',
        'css/devreg/login.styl',
        'css/devreg/forms.styl',
        'css/ecosystem/landing.styl',
        'css/ecosystem/documentation.styl',
    ),
    'mkt/in-app-payments': (
        'css/devreg/reset.styl',
        'css/devreg/consumer-typography.styl',
        'css/devreg/buttons.styl',
        'css/devreg/in-app-payments.styl',
    ),
    'mkt/in-app-products': (
        'css/devreg/in-app-products.styl',
    ),
    'mkt/lookup': (
        'css/devreg/manifest.styl',
        'css/devreg/lookup-tool.styl',
        'css/devreg/activity.styl',
    ),
    'mkt/gaia': (
        # Gaia building blocks.
        'css/gaia/action_menu.css',
        'css/gaia/switches.css',
        'css/gaia/value_selector.css',
    ),
    'mkt/operators': (
        'css/devreg/legacy-paginator.styl',
        'css/devreg/data-grid.styl',
        'css/devreg/operators.styl',
    ),
}

JS = {
    # Used by the File Viewer for packaged apps.
    'zamboni/files': (
        'js/lib/diff_match_patch_uncompressed.js',
        'js/lib/syntaxhighlighter/xregexp-min.js',
        'js/lib/syntaxhighlighter/shCore.js',
        'js/lib/syntaxhighlighter/shLegacy.js',
        'js/lib/syntaxhighlighter/shBrushAppleScript.js',
        'js/lib/syntaxhighlighter/shBrushAS3.js',
        'js/lib/syntaxhighlighter/shBrushBash.js',
        'js/lib/syntaxhighlighter/shBrushCpp.js',
        'js/lib/syntaxhighlighter/shBrushCSharp.js',
        'js/lib/syntaxhighlighter/shBrushCss.js',
        'js/lib/syntaxhighlighter/shBrushDiff.js',
        'js/lib/syntaxhighlighter/shBrushJava.js',
        'js/lib/syntaxhighlighter/shBrushJScript.js',
        'js/lib/syntaxhighlighter/shBrushPhp.js',
        'js/lib/syntaxhighlighter/shBrushPlain.js',
        'js/lib/syntaxhighlighter/shBrushPython.js',
        'js/lib/syntaxhighlighter/shBrushSass.js',
        'js/lib/syntaxhighlighter/shBrushSql.js',
        'js/lib/syntaxhighlighter/shBrushVb.js',
        'js/lib/syntaxhighlighter/shBrushXml.js',
        'js/zamboni/storage.js',
        'js/zamboni/files.js',
    ),
    'mkt/devreg': (
        # tiny module loader
        'js/lib/amd.js',

        'js/lib/jquery-1.11.1.js',
        'js/lib/underscore.js',
        'js/lib/format.js',
        'js/lib/jquery.cookie.js',
        'js/lib/stick.js',
        'js/common/fakefilefield.js',
        'js/devreg/gettext.js',
        'js/devreg/tracking.js',
        'js/devreg/init.js',  # This one excludes buttons initialization, etc.
        'js/devreg/modal.js',
        'js/devreg/overlay.js',
        'js/devreg/capabilities.js',
        'js/devreg/slugify.js',
        'js/devreg/formdata.js',
        'js/devreg/tooltip.js',
        'js/devreg/popup.js',
        'js/devreg/login.js',
        'js/devreg/notification.js',
        'js/devreg/storage.js',
        'js/devreg/utils.js',
        'js/lib/csrf.js',
        'js/lib/document-register-element.js',

        'js/impala/serializers.js',
        'js/common/keys.js',
        'js/common/upload-base.js',
        'js/common/upload-packaged-app.js',
        'js/common/upload-image.js',

        'js/devreg/l10n.js',
        'js/zamboni/storage.js',  # Used by editors.js, devhub.js

        # jQuery UI
        'js/lib/jquery-ui/jquery-ui-1.10.1.custom.js',
        'js/lib/jquery.minicolors.js',

        'js/devreg/devhub.js',
        'js/devreg/submit.js',
        'js/devreg/tabs.js',
        'js/devreg/edit.js',
        'js/devreg/validator.js',

        # Specific stuff for making payments nicer.
        'js/devreg/payments-enroll.js',
        'js/devreg/payments-manage.js',
        'js/devreg/payments.js',

        # For testing installs.
        'js/devreg/apps.js',
        'js/devreg/test-install.js',

        'js/devreg/tracking_app_submit.js',

        # IARC.
        'js/devreg/content_ratings.js',

        # Marketplace elements.
        'js/lib/marketplace-elements.js',

        # Module initialization.
        'js/devreg/devreg_init.js',
    ),
    'mkt/reviewers': (
        'js/lib/moment-with-langs.min.js',  # JS date lib.
        'js/devreg/reviewers/editors.js',
        'js/devreg/apps.js',  # Used by install.js
        'js/devreg/reviewers/payments.js',
        'js/devreg/reviewers/install.js',
        'js/devreg/reviewers/buttons.js',
        'js/devreg/manifest.js',  # Used by reviewers.js
        'js/devreg/reviewers/reviewers_commbadge.js',
        'js/devreg/reviewers/reviewers.js',
        'js/devreg/reviewers/expandable.js',
        'js/devreg/reviewers/mobile_review_actions.js',
        'js/common/fakefilefield.js',
        # Used by Reviewer Attachments in devreg/init.js.
        'js/common/formsets.js',
        'js/devreg/reviewers/reviewers_init.js',
    ),
    'mkt/in-app-payments': (
        'js/lib/jquery-1.11.1.js',
        'js/devreg/inapp_payments.js',
        'js/devreg/utils.js',
        'js/lib/csrf.js',
        'js/impala/serializers.js',
        'js/devreg/login.js',
        'js/devreg/storage.js',
    ),
    'mkt/in-app-products': (
        'js/lib/es5-shim.min.js',  # We might already assume these work.
        'js/lib/flight.min.js',
        'js/devreg/in_app_products.js',
    ),
    'mkt/lookup': (
        'js/common/keys.js',
        'js/impala/ajaxcache.js',
        'js/devreg/suggestions.js',
        'js/devreg/manifest.js',
        'js/devreg/lookup-tool.js',
    ),
    'mkt/ecosystem': (
        'js/devreg/ecosystem.js',
    )

}
