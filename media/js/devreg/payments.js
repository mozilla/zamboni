define('payments', [], function() {
    'use strict';

    var currentPrice;
    var $regions = $('#region-list');
    var $regionsIsland = $('#regions');
    var $regionCheckboxes = $regions.find('input[type=checkbox]');

    var regionsData = $regions.data();

    var allPaidRegionIds = regionsData.allPaidRegionIds;
    var apiErrorMsg = regionsData.apiErrorMsg;
    var tierZeroId = regionsData.tierZeroId;
    var notApplicableMsg = regionsData.notApplicableMsg;
    var paymentMethods = regionsData.paymentMethods || {};
    var pricesApiEndpoint = regionsData.pricelistApiUrl + '{0}/';
    var $tdNodes = $('<td class="cb"></td><td class="lp"></td><td class="lm"></td>');
    var $paidRegionTableTbody = $('#paid-regions tbody');
    var providerLookup = regionsData.providerLookup;
    var enabledProviderIds = regionsData.enabledProviderIds;

    var providerIdLookup = {};
    if (providerLookup) {
        Object.keys(providerLookup).forEach(function(k) {
            providerIdLookup[providerLookup[k]] = k;
        });
    }

    function getOverlay(opts) {
        var id = opts;
        if (_.isObject(opts)) {
            if (opts.provider) {
                id = [opts.provider, opts.id].join('-');
            } else {
                id = opts.id;
            }
        }
        $('.overlay').remove();
        z.body.addClass('overlayed');
        var overlay = makeOrGetOverlay(opts);
        overlay.html($('#' + id + '-template').html())
               .addClass('show')
               .data('provider', opts.provider)
               .on('click', '.close', _pd(function() {
                   overlay.trigger('overlay_dismissed').remove();
               }));
        return overlay;
    }

    function setupPaymentAccountOverlay($overlay, onsubmit) {
        $overlay.on('submit', 'form', _pd(function() {
            var $form = $(this);
            var $waiting_overlay = getOverlay({
                id: 'payment-account-waiting',
                class: 'payment-account-overlay',
                provider: $overlay.data('provider'),
            });
            var $old_overlay = $overlay.children('section');
            $old_overlay.detach();
            $form.find('.error').remove();

            $.post(
                $form.attr('action'), $form.serialize(),
                function(data) {
                    $waiting_overlay.trigger('dismiss');
                    onsubmit.apply($form, [data]);
                }
            ).error(function(error_data) {
                // If there's an error, revert to the form and reset the buttons.

                // We're recycling the variable $waiting_overlay to store
                // the old overlay. That gets cleaned up, though, when we
                // re-call setupBangoForm().
                $waiting_overlay.empty().append($old_overlay);

                try {
                    var parsed_errors = JSON.parse(error_data.responseText);
                    for (var field_error in parsed_errors) {
                        var field = $('#id_' + field_error);
                        $('<div>').addClass('error')
                                  .insertAfter(field)
                                  .text(parsed_errors[field_error]);
                    }
                    // If the error occurred on an unknown field,
                    // stick the error at the top. Maybe with more detail.
                    if (parsed_errors.__all__ !== null) {
                        var target = $old_overlay.find('#payment-account-errors');
                        $('<div>').addClass('error')
                                  .insertAfter(target)
                                  .text(parsed_errors.__all__);
                    }
                } catch(err) {
                    // There was a JSON parse error, just stick the error
                    // message on the form.
                    console.error('Got', err, 'when parsing', error_data.responseText);
                    $old_overlay.find('#payment-account-errors')
                                .append($('<p class="error"></p>').text(apiErrorMsg));
                }

                // Re-initialize the form submit binding.
                setupPaymentAccountOverlay($waiting_overlay, onsubmit);
            });
        }));
    }

    function moveAnimate(element, newParent, $elmToRemove, zIndex) {
        zIndex = zIndex || 100;
        var $element = $(element);
        var $newParent = $(newParent);
        var oldOffset = $element.offset();

        $element.appendTo($newParent);
        var newOffset = $element.offset();
        var $temp = $element.clone().appendTo('body');
        $temp.css({'position': 'absolute',
                   'left': oldOffset.left,
                   'top': oldOffset.top,
                   'zIndex': zIndex});

        element.hide();
        $temp.animate({top: parseInt(newOffset.top, 10),
                       left: parseInt(newOffset.left, 10)},
                      'slow', function() {
            $temp.remove();
            $element.show();
            if ($elmToRemove) {
                $elmToRemove.hide(500, function() { this.remove(); });
            }
        });
    }

    function createTableRow(checkBox, ident, localPriceText, localMethodText, provider) {
        var $tds = $tdNodes.clone();
        var $tr = $paidRegionTableTbody.find('tr[data-region="' + ident + '"]');
        var $checkBoxContainer = $($tds[0]);
        var $localPriceContainer = $($tds[1]);
        var $localMethodContainer = $($tds[2]);
        $localMethodContainer.text(localMethodText + ' (' + provider + ')');
        $localPriceContainer.text(localPriceText);
        $tr.append($tds);
        return $tr;
    }

    function updatePrices(force) {

        /*jshint validthis:true */

        var $this = $(this);
        var selectedPrice = $this.val();

        if (!selectedPrice) {
            return;
        }

        // If free with in-app is selected, check "Yes" then make the 'No' radio
        // disabled and hide it. Also hide upsell as that's not relevant.
        if (selectedPrice == 'free') {
            $('input[name=allow_inapp][value=True]').prop('checked', true);
            $('input[name=allow_inapp][value=False]').prop('disabled', true)
                                                     .parent('label').hide();
            $('#paid-upsell-island').hide();

            // For free apps we are using the same data for tier zero apps
            // to populate the region list.
            selectedPrice = tierZeroId;
        } else {
            $('#paid-upsell-island').show();
            $('input[name=allow_inapp][value=False]').prop('disabled', false)
                                                     .parent('label').show();
        }

        // From here on numbers should be used.
        selectedPrice = parseInt(selectedPrice, 10);

        // No-op if nothing else has changed.
        if (currentPrice === selectedPrice && !force) {
            return;
        }

        $.ajax({
            url: format(pricesApiEndpoint, selectedPrice),
            beforeSend: function() {
                $regionsIsland.addClass('loading');
            },
            success: function(data) {
                var moveQueue = [];
                var prices = data.prices || [];
                var seenCheckBoxes = [];
                var seenRegions = [];
                var tierPrice = data.price;

                // Iterate over the prices for the regions
                for (var i=0, j=prices.length; i<j; i++) {
                    var price = prices[i];
                    var regionId = price.region;
                    var regionSeen = seenRegions.indexOf(regionId) > -1;

                    if (enabledProviderIds.indexOf(price.provider) === -1) {
                        continue;
                    }

                    if (!regionSeen) {
                        seenRegions.push(regionId);
                    }

                    var billingMethodText = paymentMethods[parseInt(price.method, 10)] || '';
                    var localPrice = price.price + ' ' + price.currency;
                    var localMethod = selectedPrice === tierZeroId ? notApplicableMsg : billingMethodText;

                    var provider = providerLookup[price.provider];
                    if (provider) {
                        provider = provider.charAt(0).toUpperCase() + provider.substring(1);
                    }

                    // If the checkbox we're interested is already in the table just update it.
                    // Otherwise we need to create a new tableRow and move it into position.
                    var $chkbox = $regions.find('input:checkbox[value=' + regionId + ']');
                    var $row = $('#paid-regions tr[data-region=' + regionId + ']');

                    // If we've already dealt with this region append this provider to existing row and continue.
                    if (regionSeen && $row.length) {
                        var $billingMethodCell = $row.find('.lm');
                        $billingMethodCell.text($billingMethodCell.text() + ', ' + localMethod + ' (' + provider + ')');
                        continue;
                    }

                    if ($row.length) {
                        if ($row.find('td').length) {
                            $row.find('.lp').text(localPrice);
                            $row.find('.lm').text(localMethod + ' (' + provider + ')');
                        } else {
                            var $tr = createTableRow($chkbox.closest('label'), regionId, localPrice, localMethod, provider);
                            moveQueue.push([$chkbox.closest('label'), $tr.find('.cb')]);
                            $chkbox.closest('li').hide(500);
                        }
                        seenCheckBoxes.push($chkbox[0]);
                    } else {
                        console.log('No row found with regionId "' + regionId + '" (noop)');
                    }
                }

                for (var k=0, l=moveQueue.length; k<l; k++) {
                    var current = moveQueue[k];
                    moveAnimate(current[0], current[1]);
                }

                $('#paid-regions input[type=checkbox]').not(seenCheckBoxes).each(function() {
                    // If the item we don't want here is in the table then we need to move it back
                    // out of the table and destroy the row contents.
                    var $chkbox = $(this);
                    var region = $chkbox.val();

                    // Lookup the location of the original checkbox so we know where to send this back to
                    var $newParent = $('.checkbox-choices li[data-region=' + region + ']');
                    $newParent.show(500);
                    var $label = $chkbox.closest('label');
                    if ($label.length) {
                        var $tds = $chkbox.closest('tr').find('td');
                        moveAnimate($label, $newParent, $tds);
                    }
                });

                $('.paid-regions input[name="regions"][value="1"]:checked').trigger('change', [true]);
            },
            dataType: "json"
        }).fail(function() {
            z.doc.trigger('notify', { 'msg': apiErrorMsg });
        }).always(function() {
            $regionsIsland.removeClass('loading');
        });

        currentPrice = selectedPrice;
    }

    function init() {
        var $priceSelect = $('#id_price');
        $('#regions').trigger('editLoaded');

        $('.update-payment-type button').click(function() {
            $('input[name=toggle-paid]').val($(this).data('type'));
        });

        var $paid_island = $('#paid-island, #paid-upsell-island, #paid-regions-island');
        var $free_island = $('#regions-island');
        $('#submit-payment-type.hasappendix').on('tabs-changed', function(e, tab) {
            $paid_island.toggle(tab.id == 'paid-tab-header');
            $free_island.toggle(tab.id == 'free-tab-header');
        });

        z.doc.on('change', '.paid-regions input[name="regions"][value="1"]', function() {
            $('#regions .rest-of-world').toggle();
        });

        if ($('#paid-regions-island').length) {
            // Paid apps for the time being must be restricted.
            var $restricted = $('input[name=restricted]');

            // Remove the first radio button for
            // "Make my app available everywhere."
            $restricted.filter('[value="0"]').closest('li').remove();

            // Keep the label but hide the radio button for
            // "Choose where my app is available."
            $restricted.filter('[value="1"]').prop('checked', true).hide();

            // Show the restricted fields (the checkboxes) which would be
            // otherwise hidden (for free apps).
            $('.restricted').removeClass('hidden');
        } else {
            // Free apps can toggle between restricted and not.
            z.doc.on('change', '#regions input[name=restricted]:checked', function(e, init) {
                // Coerce string ('0' or '1') to boolean ('true' or 'false').
                var restricted = !!+$(this).val();
                $('.restricted').toggle(restricted);
                $('.unrestricted').toggle(!restricted);
                if (!init) {
                    window.location.hash = 'regions-island';
                }
            });
            $('#regions input[name=restricted]:checked').trigger('change', [true]);
        }

        // Update prices to reflect the regions available.
        $priceSelect.on('change', updatePrices);
        updatePrices.call($priceSelect[0]);
    }

    $('body').on('app-payment-account-deletion', function(e, data) {
        var providerId = providerIdLookup[data.provider];
        if (providerId) {
            var idx = enabledProviderIds.indexOf(parseInt(providerId, 10));
            if (idx > -1) {
                enabledProviderIds.splice(idx, 1);
                console.log('Updating prices');
                updatePrices.call($('#id_price')[0], true);
            }
        }
    });

    return {
        getOverlay: getOverlay,
        setupPaymentAccountOverlay: setupPaymentAccountOverlay,
        init: init
    };
});

if ($('.payments.devhub-form').length) {
    require('payments').init();
    require('payments-enroll').init();
    require('payments-manage').init();
}
