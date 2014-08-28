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
});
