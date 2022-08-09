(function($) {
    $(function() {
        $('.grp-filter-choice').select2({width: '100%'}).on('change', function () {
            location.href = $(this).val();
        });
    });
})(django.jQuery);
