function stringToCoordinates(coordinate) {
    var latLng = coordinate.split(',').map(parseFloat);
    return {lat: latLng[0], lng: latLng[1]};
}

function locationToFloat(coordinate) {
    return {lat: parseFloat(coordinate.lat), lng: parseFloat(coordinate.lng)};
}

var colors = [
    '#BF4040', '#BF4A40', '#BF5540', '#BF6040', '#BF6A40', '#BF7540', '#BF8040', '#BF8A40', '#BF9540', '#BF9F40',
    '#BFAA40', '#BFB540', '#BFBF40', '#B5BF40', '#AABF40', '#9FBF40', '#95BF40', '#8ABF40', '#7FBF40', '#75BF40',
    '#6ABF40', '#60BF40', '#55BF40', '#4ABF40', '#40BF40', '#3FBE4A', '#40BF55', '#40BF60', '#40BF6A', '#40BF75',
    '#40BF7F', '#40BF8A', '#40BF95', '#40BF9F', '#40BFAA', '#40BFB5', '#40BFBF', '#40B5BF', '#40AABF', '#409FBF',
    '#4095BF', '#408ABF', '#4080BF', '#4075BF', '#406ABF', '#4060BF', '#4055BF', '#404ABF', '#4040BF', '#4A40BF',
    '#5540BF', '#6040BF', '#6A40BF', '#7540BF', '#8040BF', '#8A40BF', '#9540BF', '#9F40BF', '#AA40BF', '#B540BF',
    '#BF40BF', '#BF40B5', '#BF40AA', '#BF409F', '#BF4095', '#BF408A', '#BF407F', '#BF4075', '#BF406A', '#BF4060',
    '#BF4055', '#BF404A'
]

function addDiffToLocation(latLng) {
    return {
        'lat': latLng.lat + ((Math.random()-0.5) / 2000),
        'lng': latLng.lng + ((Math.random()-0.5) / 2000)
    }
}

function drawJobMarker(coordinates, color, map, title, label) {
    var pinSVGFilled = "M 12,2 C 8.1340068,2 5,5.1340068 5,9 c 0,5.25 7,13 7,13 0,0 7,-7.75 7,-13 0,-3.8659932 -3.134007,-7 -7,-7 z";
    var labelOriginFilled =  new google.maps.Point(12,9);

    var markerImage = {  // https://developers.google.com/maps/documentation/javascript/reference/marker#MarkerLabel
        path: pinSVGFilled,
        anchor: new google.maps.Point(12,17),
        fillOpacity: 1,
        fillColor: color,
        strokeWeight: 1,
        strokeColor: "white",
        scale: 1,
        labelOrigin: labelOriginFilled
    };
    var label = {
        text: label,
        color: "white",
        fontSize: "8px",
    }; // https://developers.google.com/maps/documentation/javascript/reference/marker#Symbol
    return new google.maps.Marker({
        map: map,
        title: title,
        label: label,
        position: coordinates,
        icon: markerImage,
    });
}


function drawDriverMarker(coordinates, color, map, title, label) {
    var pinSVGHole = "M12,11.5A2.5,2.5 0 0,1 9.5,9A2.5,2.5 0 0,1 12,6.5A2.5,2.5 0 0,1 14.5,9A2.5,2.5 0 0,1 12,11.5M12,2A7,7 0 0,0 5,9C5,14.25 12,22 12,22C12,22 19,14.25 19,9A7,7 0 0,0 12,2Z";
    var labelOriginHole = new google.maps.Point(12,15);

    var markerImage = {  // https://developers.google.com/maps/documentation/javascript/reference/marker#MarkerLabel
        path: pinSVGHole,
        anchor: new google.maps.Point(12,17),
        fillOpacity: 1,
        fillColor: color,
        strokeWeight: 1,
        strokeColor: "white",
        scale: 1,
        labelOrigin: labelOriginHole
    };
    var label = {
        text: label,
        color: "white",
        fontSize: "8px",
    }; // https://developers.google.com/maps/documentation/javascript/reference/marker#Symbol
    return new google.maps.Marker({
        map: map,
        title: title,
        label: label,
        position: coordinates,
        icon: markerImage,
    });
}


function generateTitle(jobObj, position, cluster_index) {
    var result = ''
    if (jobObj) {
        result += ('Id:' + jobObj.id + '\n')
    }
    if (position) {
        result += ('Lat:' + position.lat.toFixed(4) + ';Lng:' + position.lng.toFixed(4) + '\n')
    }
    if (jobObj) {
        result += ('From:' + jobObj.deliver_after + '\n')
        result += ('To:' + jobObj.deliver_before + '\n')
        if (jobObj.skill_set.length) {
            result += ('Skills:' + jobObj.skill_set + '\n')
        }
        result += ('Pre-assigned Driver:' + jobObj.driver_member_id + '\n')
    }
    result += 'Cluster#' + cluster_index;
    return result;
}

function generateDriverTitle(driver, position, cluster_index) {
    var result = ''
    result += ('Id:' + driver.id + '\n')
    if (position) {
        result += ('Current Lat:' + position.lat.toFixed(4) + ';Lng:' + position.lng.toFixed(4) + '\n')
    }
    result += ('Start shift:' + driver.start_time + '\n')
    result += ('End shift:' + driver.end_time + '\n')
    result += ('Capacity:' + driver.capacity + '\n')
    if (driver.skill_set.length) {
        result += ('Skills:' + driver.skill_set + '\n')
    }
    if (driver.start_hub){
        var coordinates = stringToCoordinates(driver.start_hub.location);
        result += ('Start hub Lat:' + coordinates.lat.toFixed(4) + ';Lng:' + coordinates.lng.toFixed(4) + '\n')
    } else if (driver.start_location){
        var coordinates = stringToCoordinates(driver.start_location.location);
        result += ('Start location Lat:' + coordinates.lat.toFixed(4) + ';Lng:' + coordinates.lng.toFixed(4) + '\n')
    }
    if (driver.end_hub){
        var coordinates = stringToCoordinates(driver.end_hub.location);
        result += ('End hub Lat:' + coordinates.lat.toFixed(4) + ';Lng:' + coordinates.lng.toFixed(4) + '\n')
    } else if (driver.end_location){
        var coordinates = stringToCoordinates(driver.end_location.location);
        result += ('End location Lat:' + coordinates.lat.toFixed(4) + ';Lng:' + coordinates.lng.toFixed(4) + '\n')
    }
    result += 'Cluster#' + cluster_index;
    return result;
}


function initMap() {
    console.log(clusters);
    if (!clusters.length) {
        alert('Empty RO');
        return;
    }
    var center = stringToCoordinates(clusters[0].params.jobs[0].deliver_address);
    var map = new google.maps.Map(document.getElementById('map'), {
        zoom: 11,
        center: center,
        mapTypeId: 'roadmap'
    });
    var legendParent = document.getElementById('legend');
    var legend = document.getElementById('legendDiv');
    var drawButton = document.getElementById('drawButton');

    var enabledClusters = {};
    for (var cluster_index = 0; cluster_index < clusters.length; cluster_index++) {
        enabledClusters[cluster_index] = true;
    }

    function getCheckboxListener(cluster_index) {
        var currentCheckbox = document.querySelector('#cluster_index'+ cluster_index);
        currentCheckbox.addEventListener('change', () => {
            enabledClusters[cluster_index] = currentCheckbox.checked;
        });
    }

    drawButton.addEventListener("click", function () {
        clear();
        drawRoutes();
     });

    var mapObjects = [];

    function clear() {
        for (var i in mapObjects) {
            mapObjects[i].setMap(null);
        }
        mapObjects = [];
        var child = legend.lastElementChild;
        while (child) {
            legend.removeChild(child);
            child = legend.lastElementChild;
        }
    }

    function drawRoutes() {
        var color_index = 0;
        var color_step = null;
        var toursToShow = 0;
        for (var cluster_index = 0; cluster_index < clusters.length; cluster_index++) {
            if (!enabledClusters[cluster_index]) {
                continue;
            }
            var cluster = clusters[cluster_index];
            toursToShow = toursToShow + Object.keys(cluster.result.drivers_tours).length;
        }
        color_step = Math.floor(colors.length/toursToShow);

        for (var cluster_index = 0; cluster_index < clusters.length; cluster_index++) {
            var cluster = clusters[cluster_index];
            var color = colors[color_index];
            var div = document.createElement('div');
            var isChecked = enabledClusters[cluster_index] ? ' checked' : '';
            div.innerHTML = '<input type="checkbox" id="cluster_index'+ cluster_index +'"'+ isChecked +'> <span style="border-bottom: solid 10px' + color + ';"></span> Cluster#' + cluster_index + '; Jobs:' + cluster.params.jobs.length + '; Drivers:' + cluster.params.drivers.length;
            legend.appendChild(div);
            getCheckboxListener(cluster_index);
            if (!enabledClusters[cluster_index]) {
                continue;
            }

            for (var tour_index in cluster.result.drivers_tours) {
                var tour = cluster.result.drivers_tours[tour_index];
                var color = colors[color_index];
                var tourPolylinePath = [];
                var driver = cluster.params.drivers.find(o => o.member_id === parseInt(tour_index));
                for (var point_index in tour.points) {
                    var point = tour.points[point_index];
                    if (point.point_kind === 'hub' | point.point_kind === 'location') {
                        var location = addDiffToLocation(locationToFloat(point.location));
                        tourPolylinePath.push(location);
                        mapObjects.push(drawDriverMarker(location, color, map, generateDriverTitle(driver, locationToFloat(point.location), cluster_index), point_index));
                    } else {
                        var location = addDiffToLocation(locationToFloat(point.location));
                        tourPolylinePath.push(location);
                        var jobObj = cluster.params.jobs.find(o => o.id === point.point_prototype.id);
                        mapObjects.push(drawJobMarker(location, color, map, generateTitle(jobObj, locationToFloat(point.location), cluster_index), point_index));
                    }
                }
                var tourPolyline = new google.maps.Polyline({
                    path: tourPolylinePath,
                    geodesic: true,
                    strokeColor: color,
                    strokeOpacity: 1,
                    strokeWeight: 2
                });
                tourPolyline.setMap(map);
                mapObjects.push(tourPolyline);
                color_index = color_index + color_step;
            }
        }
    }

    drawRoutes();
    map.controls[google.maps.ControlPosition.RIGHT_BOTTOM].push(legendParent);
}