var $ = django.jQuery;
$(document).ready(function () {
    let getUrl = window.location;
    let url = getUrl.protocol + "//" + getUrl.host + '/admin/driverhubs' + "?";

    $('#id_merchant').on('change', function () {
        let merchant_id = $(this).val();

        $.ajax({
            url: url,
            data: {
                'merchant': merchant_id,
            },
            success: function (data) {
                $("#id_hub").empty();
                $.each(data.hubs, function(index, value) {
                    $("#id_hub").append($('<option>', { value : value.id })
                        .text(value.name));
                });
                $("#id_driver").empty();
                $.each(data.drivers, function(index, value) {
                    $("#id_driver").append($('<option>', { value : value.id })
                        .text(value.first_name + ' ' + value.last_name));
                });
            }
        });

    });

});