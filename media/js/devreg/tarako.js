jQuery(function ($) {
    $('#request-tarako').on('submit', function (e) {
        e.preventDefault();
        var $form = $(this);
        var $errorField = $form.find('.error');
        $errorField.text('');

        $.post($form.attr('action'), {
            app: $form.find('[name="app"]').val(),
            queue: $form.find('[name="queue"]').val(),
        }).done(function (review) {
            window.location = window.location;
        }).fail(function (response) {
            var errors = response.responseJSON;
            if (errors.app) {
                $errorField.text("Your app " + errors.app[0]);
            } else {
                $errorField.text("An error occurred.");
            }
        });
    });

    var $removeTarakoModal = $('#modal-remove-tarako');
    $removeTarakoModal.modal('#remove-tarako', {width: 400});
    var $removeTarakoTag = $('#remove-tarako-tag');
    $removeTarakoTag.on('click', function (e) {
        $.ajax({
            url: $removeTarakoTag.data('action'),
            method: 'delete',
        }).done(function () {
            window.location = window.location;
        }).fail(function () {
            console.error('Error removing tarako tag');
            $removeTarakoModal.find('.error').text(
              gettext('Something went wrong. Please try again.'));
        });
    });
});
