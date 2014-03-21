(function(exports) {
    "use strict";

    exports.houdini = function() {
        // Initialize magic labels.
        $(document).delegate('.houdini.ready .edit', 'click', _pd(function(e) {
            var $label = $(this).closest('.houdini');
            $label.addClass('fading');
            setTimeout(function() {
                $label.removeClass('ready').addClass('active');
            }, 500);
        })).delegate('.houdini.active .done', 'click', _pd(function(e) {
            var $label = $(this).closest('.houdini');
            $label.removeClass('active').addClass('ready');
            // Replace text with new value.
            $label.find('.output').text($label.find('input').val());
        }));
    };

    // Handle Name and Slug.
    exports.nameHoudini = function() {
        var $ctx = $('#general-details');
    };

    exports.privacy = function() {
        // Privacy Policy is required. Maybe I can reuse this elsewhere.
        var $ctx = $('#show-privacy');
        // When the checkbox is clicked ...
        $ctx.delegate('input[type=checkbox]', 'click', function() {
            // Hide the label ...
            $ctx.find('label.checkbox').slideUp(function() {
                // And show the Privacy Policy field ...
                $ctx.find('.brform').slideDown(function() {
                    $ctx.addClass('active');
                });
            });
        });
    };

    var $compat_save_button = $('#compat-save-button'),
        isSubmitAppPage = $('#page > #submit-payment-type').length;

    // Reset selected device buttons and values.
    $('#submit-payment-type h2 a').click(function(e) {
        if ($(this).hasClass('disabled') || $compat_save_button.length) {
            return;
        }

        if (isSubmitAppPage) {
            nullifySelections();
        }
    });

    $('#submit-payment-type a.choice').on('click',
        _pd(function() {
            var $this = $(this),
                free_or_paid = this.id.split('-')[0],
                $input = $('#id_' + free_or_paid + '_platforms'),
                old = $input.val() || [],
                val = $this.data('value'),
                nowSelected = old.indexOf(val) === -1;

            if (nowSelected) {
                old.push(val);
            } else {
                delete old[old.indexOf(val)];
            }
            $this.toggleClass('selected', nowSelected);
            $this.find('input').prop('checked', nowSelected);
            $input.val(old).trigger('change');
            $compat_save_button.removeClass('hidden');
            setTabState();
        })
    );

    // Handle clicking of form_factors.
    //
    // When responsive is clicked, we check all form factors. This also handles
    // unclicking and all the variations in between.
    $('#submit-form-factor a.form_factor_choice').on('click', _pd(function() {
        var $this = $(this);
        var $input = $('#id_form_factors');
        var vals = $input.val() || [];
        var val = $this.attr('data-value');
        var selected = $this.toggleClass('selected').hasClass('selected');
        var $responsive = $('#form-factor-responsive');

        function update_vals(vals, selected, val) {
            if (selected) {
                if (vals.indexOf(val) === -1) {
                    vals.push(val);
                }
            } else {
                vals.splice(vals.indexOf(val), 1);
            }
        }

        if (val === 'responsive') {
            // Handle responsive option.
            $('.form-factor-choices a.form-fields').each(function(i, e) {
                var $e = $(e);
                $e.toggleClass('selected', selected);
                update_vals(vals, selected, $e.attr('data-value'));
            });
        } else {
            // Handle other options, single item selected.
            update_vals(vals, selected, val);

            // Handle cases where we need to turn on/off responsive button.
            if (!selected && $responsive.hasClass('selected')) {
                // If deselected but responsive is still selected.
                $responsive.removeClass('selected');
            } else if (selected && !$responsive.hasClass('selected')) {
                // If selected but responsive is not selected, check others.
                var enable = true;
                $('.form-factor-choices a.form-fields').each(function(i, e) {
                    if (!$(e).hasClass('selected')) {
                        enable = false;
                    }
                });
                if (enable) {
                    $responsive.addClass('selected');
                }
            }
        }

        // If mobile (form factor id=2) is the only option selected, set the
        // qHD buchet flag.
        var mobile_id = $('#form-factor-mobile').attr('data-value');
        $('#id_has_qhd').prop('checked', (
            vals.length === 1 && vals[0] === mobile_id)).trigger('change');

        $input.val(vals).trigger('change');
        $compat_save_button.removeClass('hidden');
    }));

    function nullifySelections() {
        $('#submit-payment-type a.choice').removeClass('selected')
            .find('input').removeAttr('checked');

        $('#id_free_platforms, #id_paid_platforms').val([]);
    }

    // Best function name ever?
    function allTabsDeselected() {
        var freeTabs = $('#id_free_platforms option:selected').length;
        var paidTabs = $('#id_paid_platforms option:selected').length;

        return freeTabs === 0 && paidTabs === 0;
    }

    // Condition to show packaged tab...ugly but works.
    function showPackagedTab() {
        // If the Android flag is disabled, and you tried to select
        // Android... no packaged apps for you.
        // (This lets us prevent you from marking your app as compatible
        // with both Firefox OS *and* Android when Android support
        // hasn't landed yet.)
        if (!$('[data-packaged-platforms~="android"]').length &&
            $('option[value*="-android"]:selected').length) {
            return false;
        }

        // If the Desktop flag is disabled, and you tried to select
        // Desktop... no packaged apps for you.
        if (!$('[data-packaged-platforms~="desktop"]').length &&
            $('option[value$="-desktop"]:selected').length) {
            return false;
        }

        return ($('#id_free_platforms option[value="free-firefoxos"]:selected').length &&
            $('#id_free_platforms option:selected').length == 1) ||
            $('#id_paid_platforms option[value="paid-firefoxos"]:selected').length ||
            $('[data-packaged-platforms~="android"] option[value*="-android"]:selected').length ||
            $('[data-packaged-platforms~="desktop"] option[value$="-desktop"]:selected').length ||
            allTabsDeselected();
    }

    // Toggle packaged/hosted tab state.
    function setTabState() {
        if (!$('#id_free_platforms, #id_paid_platforms').length) {
            return;
        }

        // If only free-os or paid-os is selected, show packaged.
        if (showPackagedTab()) {
            $('#packaged-tab-header').css('display', 'inline');
        } else {
            $('#packaged-tab-header').hide();
            $('#hosted-tab-header').find('a').click();
        }
    }

    z.body.on('tabs-changed', function(e, tab) {
        if (tab.id == 'packaged-tab-header') {
            $('.learn-mdn.active').removeClass('active');
            $('.learn-mdn.packaged').addClass('active');
        } else if (tab.id == 'hosted-tab-header') {
            $('.learn-mdn.active').removeClass('active');
            $('.learn-mdn.hosted').addClass('active');
        }
    });

    // Deselect all checkboxes once tabs have been setup.
    if (isSubmitAppPage) {
        $('.tabbable').bind('tabs-setup', nullifySelections);
    } else {
        // On page load, update the big device buttons with the values in the form.
        $('#upload-webapp select').each(function(i, e) {
            $.each($(e).val() || [], function() {
                $('#submit-payment-type #' + this).addClass('selected');
            });
        });
    }

})(typeof exports === 'undefined' ? (this.submit_details = {}) : exports);


$(document).ready(function() {

    // Anonymous users can view the Developer Agreement page,
    // and then we prompt for log in.
    if (z.anonymous && $('#submit-terms').length) {
        var $login = $('.overlay.login');
        $login.addClass('show');
        $('#submit-terms form').on('click', 'button', _pd(function() {
            $login.addClass('show');
        }));
    }

    // Icon previews.
    imageStatus.start(true, false);
    $('#submit-media').on('click', function(){
        imageStatus.cancel();
    });

    if (document.getElementById('submit-details')) {
        //submit_details.general();
        //submit_details.privacy();
        initCatFields();
        initCharCount();
        initSubmit();
        initTruncateSummary();
    }
    submit_details.houdini();
});
