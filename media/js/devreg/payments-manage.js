define('payments-manage', ['payments'], function(payments) {
    'use strict';

    function refreshAccountForm(data) {
        var $accountListForm = $('#' + data.provider + '-accounts-list');
        var $accountListContainer = $('#' + data.provider + '-account-list');
        $accountListForm.load($accountListContainer.data('url'));
    }

    function newBangoPaymentAccount(e) {
        var provider = e.currentTarget.attributes['data-provider'].value;
        var $overlay = payments.getOverlay({
            'id': 'payment-account-add',
            'class': 'undismissable payment-account-overlay',
            'provider': provider,
        });
        payments.setupPaymentAccountOverlay($overlay, function (data) {
            data.provider = provider;
            showAgreement(data);
        });
    }

    function confirmPaymentAccountDeletion(data) {
        var spliter = ', ';
        var isPlural = data['app-names'].indexOf(spliter) !== -1;
        var $confirm_delete_overlay = payments.getOverlay({
            id: 'payment-account-delete-confirm',
            class: 'payment-account-overlay',
        });
        var deletingAccountName = data['name'];
        // L10n: This sentence introduces a list of applications.
        $confirm_delete_overlay.find('p').text(format(ngettext(
            'Deleting payment account "{0}" will remove the payment ' +
            'account from the following apps. Applications without a ' +
            'payment account will no longer be available for sale.',
            'Deleting payment account "{0}" will remove the payment ' +
            'account from the following app. Applications without a ' +
            'payment account will no longer be available for sale.',
            isPlural),
            [deletingAccountName]));
        var $ul = $confirm_delete_overlay.find('ul');
        data['app-names'].split(spliter).forEach(function (appName) {
            var $el = $('<li/>');
            var paymentAccounts = data['app-payment-accounts'][appName];
            $el.append($('<span class="app-name"/>').text(format(gettext(
                '{appName} payment accounts:'), {appName: appName})));
            paymentAccounts.forEach(function (accountName, i, all) {
                var $nameEl = $('<span/>').text(accountName);
                if (accountName == deletingAccountName) {
                    $nameEl.addClass('deleting-account-name');
                }
                $el.append($nameEl);
                if (i < all.length - 1) {
                    $el.append(', ');
                }
            });
            $ul.append($el);
        });

        $confirm_delete_overlay.on('click', 'a.payment-account-delete-confirm', _pd(function() {
            $.post(data['delete-url']).then(function () {
                refreshAccountForm(data);
            });

            $confirm_delete_overlay.remove();
            z.body.removeClass('overlayed');
            var accountName = data.name;
            var currentAppName = data['current-app-name'];
            var paymentAccounts = data['app-payment-accounts'][currentAppName];
            // If this app is associated with the account and it only has one
            // account show the warning.
            if (paymentAccounts && paymentAccounts.length === 1) {
                $('#paid-island-incomplete').removeClass('hidden');
                $('.no-payment-regions').removeClass('hidden');
            }

            if (paymentAccounts.indexOf(accountName) > -1 && data.provider) {
                // Fire a custom event for the account deletion so we can update
                // The regions UI as necessary.
                console.log('Firing a custom event for the payment account deletion: ' +
                    JSON.stringify({account: accountName, provider: data.provider}));
                $('body').trigger('app-payment-account-deletion', {provider: data.provider});
            }

        }));
    }

    function setupAgreementOverlay(data, onsubmit) {
        var $waiting_overlay = payments.getOverlay({
            id: 'payment-account-waiting',
            class: 'payment-account-overlay',
            provider: data.provider,
        });
        var $portal_link = data['portal-link'];

        $.getJSON(data['agreement-url'], function(response) {
            var $overlay = payments.getOverlay('show-agreement');
            $overlay.on('submit', 'form', _pd(function(e) {
                var $form = $(this);

                // Assume the POST below was a success, and close the modal.
                $overlay.trigger('overlay_dismissed').detach();
                onsubmit.apply($form, data);
                if ($portal_link) {
                    $portal_link.show();
                }

                // If the POST failed, we show an error message.
                $.post(data['agreement-url'], $form.serialize(), function () {
                    refreshAccountForm(data);
                }).fail(function() {
                    $waiting_overlay.find('h2').text(gettext('Error'));
                    $waiting_overlay.find('p').text(gettext('There was a problem contacting the payment server.'));
                    if ($portal_link) {
                        $portal_link.hide();
                    }
                });
            }));

            // Plop in text of agreement.
            $('.agreement-text').html(response.text);

            if (response.accepted) {
                $overlay.find('form').trigger('submit');
            }
        });
    }

    function showAgreement(data) {
        setupAgreementOverlay(data, function() {
            refreshAccountForm(data);
            $('#no-payment-providers').addClass('js-hidden');
        });
    }

    function portalRedirect(data) {
        // Redirecting to Bango dev portal if the local redirection is successful.
        data.el.addClass('loading-submit').text('');
        $.ajax(data['portal-url'])
            .done(function(data, textStatus, jqXHR) {
                window.location.replace(jqXHR.getResponseHeader("Location"));
            }).fail(function() {
                data.el.removeClass('loading-submit').closest('td').text(gettext('Authentication error'));
            });
    }

    function editBangoPaymentAccount(account_url, provider) {
        function paymentAccountSetup() {
            var $overlay = payments.getOverlay({
                id: 'payment-account-edit',
                class: 'payment-account-overlay',
                provider: provider,
            });
            $overlay.find('form').attr('action', account_url);
            payments.setupPaymentAccountOverlay($overlay, function () {
                refreshAccountForm({provider: provider});
            });
        }

        // Start the loading screen while we get the account data.
        return function(e) {
            var $waiting_overlay = payments.getOverlay({
                id: 'payment-account-waiting',
                class: 'payment-account-overlay',
                provider: provider,
            });
            $.getJSON(account_url, function(data) {
                $waiting_overlay.remove();
                z.body.removeClass('overlayed');
                paymentAccountSetup();
                for (var field in data) {
                    $('#id_' + field).val(data[field]);
                }
            }).fail(function() {
                $waiting_overlay.find('h2').text(gettext('Error'));
                $waiting_overlay.find('p').text(gettext('There was a problem contacting the payment server.'));
            });
        };
    }

    var paymentAccountTemplate = template($('#account-row-template').html());
    function paymentAccountList(e) {
        var $overlay = payments.getOverlay('account-list');
        var $overlay_section = $overlay.children('.account-list').first();

        $.getJSON($overlay_section.data('accounts-url'), function(data) {
            $overlay_section.removeClass('loading');
            var $table = $overlay_section.children('table');
            if (data.length) {
                for (var acc = 0; acc < data.length; acc++) {
                    var account = data[acc];
                    $table.append(paymentAccountTemplate(account));
                    if (account.shared) {
                        $table.find('a.delete-account').last().remove();
                    }
                }
            } else {
                var $none = $('<div>');
                $none.text(gettext('You do not currently have any payment accounts.'));
                $none.insertBefore($table);
                $table.remove();
            }

            $overlay_section.on('click', 'a.delete-account', _pd(function() {
                var parent = $(this).closest('tr');
                var app_names = parent.data('app-names');
                var app_payment_accounts = parent.data('app-payment-accounts');
                var current_app_name = parent.data('current-app-name');
                var delete_url = parent.data('delete-url');
                if (app_names === '') {
                    $.post(delete_url)
                     .fail(function() {
                         // TODO: figure out how to display a failure.
                     })
                     .success(function() {
                         parent.remove();
                         refreshAccountForm({provider: parent.data('account-provider')});
                     });
                } else {
                    confirmPaymentAccountDeletion({
                        'app-names': app_names,
                        'app-payment-accounts': app_payment_accounts,
                        'current-app-name': current_app_name,
                        'delete-url': delete_url,
                        'name': parent.data('account-name'),
                        'shared': parent.data('shared'),
                        'provider': parent.data('account-provider'),
                    });
                }
            })).on('click', '.modify-account', _pd(function() {
                // Get the account URL from the table row and pass it to
                // the function to handle the Edit overlay.
                var $row = $(this).closest('tr');
                editBangoPaymentAccount($row.data('account-url'),
                                        $row.data('account-provider'))();
            })).on('click', '.accept-tos', _pd(function() {
                var $tr = $(this).closest('tr');
                showAgreement({
                    'agreement-url': $tr.data('agreement-url'),
                    'portal-link': $tr.closest('.portal-link'),
                    'provider': $tr.data('account-provider'),
                });
            })).on('click', '.portal-link-bango', _pd(function() {
                var $this = $(this);
                // Prevent double-click leading to an authentication error.
                $this.click(function () { return false; });
                portalRedirect({
                    'portal-url': $this.closest('tr').data('portal-url'),
                    'el': $this
                });
            }));
        });
    }

    function init() {
        z.body.on('click', '.add-payment-account', _pd(newBangoPaymentAccount));
        z.body.on('click', '#payment-account-action', _pd(paymentAccountList));
    }

    return {init: init};
});
