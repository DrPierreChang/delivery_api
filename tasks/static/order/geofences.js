var images = {
    geofence_entered: {
        name: 'Geofence entered',
        image: "https://maps.google.com/mapfiles/ms/icons/yellow-dot.png"
    },
    geofence_exited: {
        name: 'Geofence exited',
        image: "https://maps.google.com/mapfiles/ms/icons/blue-dot.png"
    },
    geofence_dwell_on_backend: {
        name: 'Geofence first entered on backend and waited for timeout',
        image: "https://maps.google.com/mapfiles/ms/icons/pink-dot.png"
    },
    geofence_entered_on_backend: {
        name: 'Geofence entered on backend',
        image: "https://maps.google.com/mapfiles/ms/icons/green-dot.png"
    },
    geofence_exited_on_backend: {
        name: 'Geofence exited on backend',
        image: "https://maps.google.com/mapfiles/ms/icons/purple-dot.png"
    }
};

var eventsNameMap = {
    geofence_entered: {True: 'geofence_entered', False: 'geofence_exited'},
    geofence_entered_on_backend: {
        entered: 'geofence_entered_on_backend',
        exited: 'geofence_exited_on_backend',
        dwell: 'geofence_dwell_on_backend'
    }

};

function stringToCoordinates(coordinate) {
    var latLng = coordinate.split(',').map(parseFloat);
    return {lat: latLng[0], lng: latLng[1]};
}

function initMap() {
    var deliverAddress = stringToCoordinates(deliver_address);

    var map = new google.maps.Map(document.getElementById('map'), {
        zoom: 17,
        center: deliverAddress
    });

    var marker = new google.maps.Marker({
        position: deliverAddress,
        map: map,
        title: 'Deliver address',
    });

    var geofenceRadius = new google.maps.Circle({
        strokeColor: '#FF0000',
        strokeOpacity: 0.8,
        strokeWeight: 2,
        fillColor: '#FF0000',
        fillOpacity: 0.35,
        map: map,
        center: deliverAddress,
        radius: 150
    });

    events.forEach(function(event){
        var eventName = eventsNameMap[event.field][event.new_value]
        new google.maps.Marker({
            position: stringToCoordinates(event.location),
            map: map,
            icon: images[eventName].image,
            title: event.happened_at
        });
    });


    var legend = document.getElementById('legend');
    for (var key in images) {
        var type = images[key];
        var name = type.name;
        var image = type.image;
        var div = document.createElement('div');
        div.innerHTML = '<img src="' + image + '">' + name;
        legend.appendChild(div);
    }

}