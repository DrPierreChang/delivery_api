var $ = django.jQuery;

$(document).ready(function () {
    let getUrl = window.location;
    let url = getUrl.protocol + "//" + getUrl.host + '/admin/survey-merchants' + "?";

    $( window ).load(function() {
        $("#id_merchant").empty();
        $("#id_sub_brand").empty();

    });
    $('#id_survey').on('change', function () {
        let survey_id = $(this).val();
        $.ajax({
            url: url,
            data: {
                'survey': survey_id,
            },
            success: function (data) {
                $("#id_merchant").empty();
                $("#id_sub_brand").empty();
                $.each(data.merchants, function(index, value) {
                    $("#id_merchant").append($('<option>', { value : value.id })
                        .text(value.name));
                });
                $.each(data.sub_brands, function(index, value) {
                    $("#id_sub_brand").append($('<option>', { value : value.id })
                        .text(value.name));
                });
            }
        });

    });

    $("#id_merchant").on('change', function () {
        let merchant_ids = $(this).val();
        let survey_id = $("#id_survey").val();
        $.ajax({
            url: url,
            data: {
                'survey': survey_id,
                'merchant_ids': merchant_ids
            },
            success: function (data) {
                $("#id_sub_brand").empty();
                $.each(data.sub_brands, function(index, value) {
                    $("#id_sub_brand").append($('<option>', { value : value.id })
                        .text(value.name));
                });
            }
        });
    });
});