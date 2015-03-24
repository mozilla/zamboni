/*
    Load notes from the Commbadge API for the app review page's review history.
*/
define('reviewersCommbadge', ['login'], function(login) {
    var $itemHistory = $('#review-files');
    var commAppUrl = $itemHistory.data('comm-app-url');
    var threadIdPlaceholder = $itemHistory.data('thread-id-placeholder');
    var noteTypes = $itemHistory.data('note-types');

    var noteTemplate = _.template($('#commbadge-note').html());
    var noResults = $('#no-notes').html();

    function _userArg(url) {
        // Persona user token.
        return urlparams(url, {'_user': login.userToken(),
                               'ordering': 'created'});
    }

    // Fetch metadata for all of the app's threads.
    $.get(_userArg(commAppUrl), function(threads) {
        // Each thread is {threadID, {version}} object.
        threads = threads.objects;

        // Show "this version has not been reviewed" for table w/ no results.
        // Gets all version IDs, then adds "No Results" to tables whose
        // data-version is not in the version IDs list.
        var versionIds = _.map(threads, function(thread) {
            return thread.version.id;
        });

        // Version ids that are actually being displayed. Useful to filter out
        // threads that we don't need to make a XHR for.
        var displayedVersions = [];

        $('table.activity').each(function(i, table) {
            var $table = $(table);
            var versionId = $table.data('version');
            if (versionIds.indexOf(versionId) === -1) {
                // No data for this table. Remove loading and add no results.
                $table.removeClass('comm-loading').find('tbody').append(noResults);
            }
            displayedVersions.push(versionId);
        });

        // Filter out useless threads...
        threads = threads.filter(function(thread) {
            return displayedVersions.indexOf(thread.version.id) !== -1;
        });

        // ... then sort them by negative version id to get the latest first,
        // since those most visible.
        threads = _.sortBy(threads, function(thread) {
            return 0 - thread.version.id;
        });

        // Now, fetch all of the notes for each thread.
        for (var i = 0; i < threads.length; i++) {
            var thread = threads[i];
            var $table = $('table.activity[data-version=' + thread.version.id + ']');
            var commNoteUrl = $itemHistory.data('comm-note-url')
                                          .replace(threadIdPlaceholder, thread.id);

            $.get(_userArg(commNoteUrl), getNoteHandler($table));
        }
    }).fail(function(e) {
        $('table.activity').html('<p class="error">' +gettext('Sorry! We had an error fetching the review history. Please try logging in again.' + '<p>')).removeClass('comm-loading');
        console.log('Login token missing: ' + require('login').userToken());
    });

    function appendNotesToTable(notes, $table) {
        // Given a list of notes, passes each note into the template
        // and appends to review history table.
        $table.find('.comm-note').remove();
        notes = notes.objects;

        for (var i = 0; i < notes.length; i++) {
            var note = notes[i];
            var author = note.author_meta.name;
            var created = moment(note.created).format('MMMM Do YYYY, h:mm:ss a');

            // Append notes to table.
            $('tbody', $table).append(noteTemplate({
                attachments: note.attachments,
                body: escape_(note.body),
                // L10n: {0} is author of note, {1} is a datetime. (e.g., "by Kevin on Feburary 18th 2014 12:12 pm").
                metadata: format(gettext('By {0} on {1}'),
                                 [author, created]),
                noteType: noteTypes[note.note_type],
                _userArg: _userArg,
            }));
        }
    }

    function getNoteHandler($table) {
        $table.removeClass('comm-loading');

        return function(notes) {
            appendNotesToTable(notes, $table);

            $table.attr('data-prev-url', notes.meta.previous);
            $table.attr('data-next-url', notes.meta.next);

            // Show/hide pagination links.
            var $paginator = $('.comm-notes-paginator', $table);
            $paginator.toggle(notes.meta.previous !== null || notes.meta.next !== null);
            $('.prev', $paginator).toggle(notes.meta.previous !== null);
            $('.next', $paginator).toggle(notes.meta.next !== null)
                                  .toggleClass('active', notes.meta.next !== null);
        };
    }

    $('.prev, .next').click(_pd(function() {
        // Fetch previous or next offset on click of paginator links..
        var $this = $(this);
        var noteUrl = $this.hasClass('next') ? 'data-next-url' : 'data-prev-url';
        var $table = $this.closest('table.activity').addClass('comm-loading');
        $.get($table.attr(noteUrl), getNoteHandler($table));
    }));
});
