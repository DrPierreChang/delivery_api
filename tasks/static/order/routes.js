function stringToCoordinates(coordinate) {
    var latLng = coordinate.split(',').map(parseFloat);
    return {lat: latLng[0], lng: latLng[1]};
}

function initMap() {
    var startingPoint = {lat: 0.0, lng: 0.0}
    var map = new google.maps.Map(document.getElementById('map'), {
        zoom: 3,
        center: startingPoint,
        mapTypeId: 'roadmap'
    });

    if (realPath) {
        realPath =  realPath.map(stringToCoordinates);
        filteredPath =  filteredPath.map(stringToCoordinates);
        startingPoint = realPath[0];
        var endPoint = realPath[realPath.length-1];

        map = new google.maps.Map(document.getElementById('map'), {
            zoom: 11,
            center: startingPoint,
            mapTypeId: 'roadmap'
        });

        var startMarker = new google.maps.Marker({
            position: startingPoint,
            map: map,
            title: 'Start point'
        });

        var endMarker = new google.maps.Marker({
            position: endPoint,
            map: map,
            title: 'End point'
        });

        var realRoute = new google.maps.Polyline({
            path: realPath,
            geodesic: true,
            strokeColor: '#EC7063',
            strokeOpacity: 1.0,
            strokeWeight: 6
        });

        var filteredRoute = new google.maps.Polyline({
            path: filteredPath,
            geodesic: true,
            strokeColor: '#5DADE2',
            strokeOpacity: 1.0,
            strokeWeight: 4
        });

        startMarker.setMap(map);
        endMarker.setMap(map);
        realRoute.setMap(map);
        filteredRoute.setMap(map);
    };

    var legendNames = {
        real: {
            name: 'Real path',
            color: '#EC7063'
        },
        filtered: {
            name: 'Filtered path',
            color: '#5DADE2'
        }
    };

    var legend = document.getElementById('legend');
    for (var key in legendNames) {
        var type = legendNames[key];
        var name = type.name;
        var color = type.color;
        var div = document.createElement('div');
        div.innerHTML = '<span style="border-bottom: solid 3px' + color + ';"></span>' + name;
        legend.appendChild(div);
    }

    map.controls[google.maps.ControlPosition.RIGHT_BOTTOM].push(legend);

}