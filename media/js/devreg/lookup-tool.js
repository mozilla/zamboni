require(['prefetchManifest']);


(function() {
    var notification = require('notification');

    $('#id_promo_img').on('change', function() {
        var preview = document.querySelector('#promo-img-preview');
        var file = this.files[0];
        var reader = new FileReader();

        reader.onloadend = function () {
          preview.src = reader.result;
        }
        if (file) {
          reader.readAsDataURL(file);
        } else {
          preview.src = '';
        }
    });

    $('.change-status button').click(_pd(function() {
        var button = $(this);
        var select = button.prev('select');
        var status = select[0].options[select[0].selectedIndex].value;
        var secret = require('login').userToken();

        button.addClass('disabled');

        $.ajax({
            url: button.data('api-url') + '?_user=' + encodeURIComponent(secret),
            data: {
                status: status
            },
            type: 'PATCH',
            dataType: 'json'
        }).done(function() {
            notification({
                message: format(gettext('Status successfully changed to "{0}"'), status),
                timeout: 2000
            });
        }).fail(function() {
            notification({
                message: format(gettext('Could not change status to "{0}"'), status),
                timeout: 2000
            });
        });
    }));

    $('.change-status select').change(function() {
        $(this).next('button').removeClass('disabled');
    });

    $('.add-group button').click(_pd(function() {
        var button = $(this);
        var select = button.parents('tr.add-group').find('select')[0];
        var group = select.options[select.selectedIndex].value;
        var group_name = select.options[select.selectedIndex].textContent;
        var secret = require('login').userToken();

        $.ajax({
            url: button.data('api-url') + '?_user=' + encodeURIComponent(secret),
            data: {
                group: group
            },
            type: button.data('api-method'),
            dataType: 'text'
        }).done(function() {
            notification({
                message: format(gettext('Group membership "{0}" added'), group_name),
                timeout: 2000
            });
            button.addClass('disabled');
            select.selectedIndex = 0;
            // add row for newly added group
            var blankrow = $('.remove-group-blank');
            var clone = blankrow.clone(true, true);
            clone.attr('class', 'remove-group');
            blankrow.before(clone);
            clone.find('td:contains("$group_name")')[0].textContent = group_name;
            clone.find('button').attr('data-api-group', group);
        }).fail(function() {
            notification({
                message: format(gettext('Could not add group "{0}"'), group_name),
                timeout: 2000
            });
        });
    }));

    $('.remove-group button, .remove-group-blank button').click(_pd(function() {
        var button = $(this);
        var group = button.data('api-group');
        var parent_row = button.parents('tr.remove-group')
        var group_name = parent_row.find('td')[0].textContent;
        var secret = require('login').userToken();

        button.addClass('disabled');

        $.ajax({
            url: button.data('api-url') + '?_user=' + encodeURIComponent(secret),
            data: {
                group: group
            },
            type: button.data('api-method'),
            dataType: 'json'
        }).done(function() {
            notification({
                message: format(gettext('Group membership "{0}" removed'), group_name),
                timeout: 2000
            });
            parent_row.remove();
        }).fail(function() {
            notification({
                message: format(gettext('Could not remove group "{0}"'), group_name),
                timeout: 2000
            });
        });
    }));

    $('.add-group select').change(function() {
        $(this).parents('tr.add-group').find('button').removeClass('disabled');
    });

    // Delete user button.
    $('#delete-user button').click(function() {
        $('#delete-user .modal-delete').show().find('textarea').focus();
    });
    $('.modal .close').click(_pd(function() {
        $(this).closest('.modal-delete').hide();
    }));

    // Search suggestions.
    $('#account-search').searchSuggestions($('#account-search-suggestions'), processResults);
    $('#app-search').searchSuggestions($('#app-search-suggestions'), processResults);
    $('#website-search').searchSuggestions($('#website-search-suggestions'), processResults);
    $('#group-search').searchSuggestions($('#group-search-suggestions'), processResults);

    // Show All Results.
    var searchTerm = '';
    z.doc.on('mousedown', '.lookup-search-form .show-all', function() {
        // Temporarily disable clearCurrentSuggestions in suggestions.js,
        // which usually runs on blur. But here we don't want this click to
        // clear the suggestions list.
        $('input[type=search]').off('blur');
    }).on('click', '.lookup-search-form .show-all', function() {
        var $form = $(this).closest('.lookup-search-form');
        // Make request for all data.
        processResults({
            data: {
                limit: 'max',
                q: searchTerm,
                type: $('[name=type] option:selected').val()
            },
            searchTerm: searchTerm,
            $results: $('.search-suggestions', $form)
        }).then(function() {
            // After loading the suggestion list, retattach blur handler.
            var handler = require('suggestions')($('.search-suggestions', $form)).delayDismissHandler;
            $('input[type=search]', $form).focus().on('blur', handler);
        });
    });

    var $lookupMeta = $('.lookup-meta');
    var searchLimit = parseInt($lookupMeta.data('search-limit'), 10);
    var maxResults = parseInt($lookupMeta.data('max-results'), 10);
    function processResults(settings) {
        if (!(settings && settings.constructor === Object)) {
            return;
        }
        var def = $.Deferred();

        var first_item = template(
            '<li><a class="sel" href="{url}"><span class="status-{status}" title="{status}">{id}</span> ' +
            '<em class="name">{name}</em> ' +
            '<em class="email">{email}</em></a></li>'
        );
        var li_item = template(
            '<li><a href="{url}"><span class="status-{status}" title="{status}">{id}</span> ' +
            '<em class="name">{name}</em> ' +
            '<em class="email">{email}</em></a></li>'
        );
        var showAllLink =
            '<li><a class="show-all no-blur">' + gettext('Show All Results') +
            '</a></li>';
        var maxSearchResultsMsg =
            '<li class="max">' + format(gettext('Over {0} results found, consider refining your search.'), maxResults) + '</li>';

        $.ajaxCache({
            url: settings.$results.attr('data-src'),
            data: settings.data || settings.$form.serialize(),
            newItems: function(formdata, items) {
                var eventName;
                if (items !== undefined) {
                    var ul = '';
                    items = items.objects;
                    $.each(items, function(i, item) {
                        var d = {
                            url: escape_(item.url) || '#',
                            id: item.id,
                            email: item.email || '',
                            name: item.name || item.display_name,
                            status: item.status || 'none'
                        };
                        if (d.url && d.id) {
                            d.name = escape_(d.name);
                            // Append the item only if it has a name.
                            if (i === 0) {
                                ul += first_item(d);
                            } else {
                                ul += li_item(d);
                            }
                        }
                    });
                    if (items.length == searchLimit) {
                        // Allow option to show all results if not already
                        // showing all results, and we know there are more results.
                        ul += showAllLink;
                    } else if (items.length == maxResults) {
                        // Show a message if max search results hit (~200).
                        ul += maxSearchResultsMsg;
                    }
                    settings.$results.html(ul);
                    searchTerm = settings.searchTerm;
                }
                settings.$results.trigger('highlight', [settings.searchTerm])
                                 .trigger('resultsUpdated', [items]);
                def.resolve();
            }
        });

        return def;
    }
})();
