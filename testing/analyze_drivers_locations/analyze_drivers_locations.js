class Driver {
    constructor(item) {
        this.item = item;
        this.orders = [];
    }
}


class Order {
    constructor(item) {
        this.item = item;
    }

    get locationsCount() {
        return this.item.serialized_track.filter((item) => item.in_progress_orders > 0).length;
    }

    get requestsCount() {
        return this.item.serialized_track.map((path_item) => {
            return path_item.google_requests;
        }).reduce((partial_sum, a) => partial_sum + a) / 2;
    }
}


let lineSymbol = {
    path: 'M 0,-1 0,1',
    strokeOpacity: 1,
    strokeColor: '#464dec',
    scale: 4
};
let routeSymbol = {
    path: 'M 0,-1 0,1',
    strokeOpacity: 0.4,
    strokeColor: '#ec01d8',
    scale: 6
};
let prevRouteSymbol = {
    path: 'M 0,-1 0,1',
    strokeOpacity: 0.6,
    strokeColor: '#43ec1c',
    scale: 6
};


function stringToCoordinates(coordinate) {
    var latLng = coordinate.split(',').map(parseFloat);
    return {lat: latLng[0], lng: latLng[1]};
}

var icons_url = {
    DELIVERY: 'https://maps.google.com/mapfiles/ms/icons/purple-dot.png',
    REAL_LOCATION: 'https://maps.google.com/mapfiles/ms/icons/yellow-dot.png',
    SNAPPED_CURRENTLY_NO_REQUESTS: 'https://maps.google.com/mapfiles/ms/icons/blue-dot.png',
    SNAPPED_WITH_REQUESTS: 'https://maps.google.com/mapfiles/ms/icons/pink-dot.png',
    SNAPPED_GOOD: 'https://maps.google.com/mapfiles/ms/icons/green-dot.png',
};

var app = angular.module('myApp', []);
app.controller('myCtrl', function($scope) {
    this.loadPathDataUrl = 'http://127.0.0.1:8000/testing/simulate_driver_path/';
    $scope.icons_url = icons_url;

    let map = null;
    $scope.drivers = [];
    $scope.chosenOrder = null;
    $scope.newRequestsCount = {count: '-'};
    $scope.chosenLocation = null;
    $scope.chosenLocationIndex = null;
    let deliveryMarker = null;
    let pathPolyline = null;
    let self = this;

    let cleaningCallbacks = [];
    let runCleanCallbacks = function() {
        while (cleaningCallbacks.length) {
            cleaningCallbacks.pop()();
        }
    };
    let addCleanCallbacks = function(mapObject) {
        let cb = () => {mapObject.setMap(null)};
        cleaningCallbacks.push(cb);
        return cb;
    };

    $scope.chooseOrder = function(order) {
        if ($scope.chosenOrder) {
            runCleanCallbacks();
        }

        $scope.chosenOrder = order;

        let deliver_address = stringToCoordinates(order.item.deliver_address.location);
        deliveryMarker = new google.maps.Marker({
            position: deliver_address,
            map: map,
            title: 'Deliver address',
            icon: icons_url.DELIVERY,
        });
        addCleanCallbacks(deliveryMarker);
        let track_coordinates = order.item.real_path.map(stringToCoordinates);
        pathPolyline = new google.maps.Polyline({
            path: track_coordinates,
            geodesic: true,
            strokeColor: '#EC7063',
            strokeOpacity: 1.0,
            strokeWeight: 6,
            map: map,
        });
        addCleanCallbacks(pathPolyline);
        track_coordinates.push(deliver_address);
        let bounds = new google.maps.LatLngBounds();
        track_coordinates.forEach((coord) => {
            bounds.extend(coord);
        });
        map.fitBounds(bounds);

        setTimeout(() => self.loadPathData(order.item), 100);
    };

    this.loadPathData = function(order) {
        let xhr = new XMLHttpRequest();
        xhr.open('POST', self.loadPathDataUrl, true);
        xhr.setRequestHeader('Content-type', 'application/json; charset=utf-8');
        console.log(JSON.stringify(order.serialized_track));
        xhr.send(JSON.stringify(order));
        let data;
        xhr.onload = (e) => {
            if (xhr.status !== 200) {
              console.log(xhr.status + ': ' + xhr.statusText);
              return;
            } else {
                data = JSON.parse(xhr.responseText);
            }

            $scope.newRequestsCount.count = data
                .filter((item) => item.requests > 0).length;
            $scope.$apply();
            self.drawPath(data);
        };
    };

    this.drawPath = function(data) {
        let currentPrevExpectedRouteCB = null;
        let currentExpectedRouteCB = null;
        let currentWindowCloseCB = null;
        let currentInitialMarkerCB = null;
        let circleCloseCB = null;

        let shouldApply = false;

        $scope.chooseOtherLocation = (change) => {
            let index = $scope.chosenLocationIndex + change;
            $scope.clearExpectedRoute();
            $scope.chosenLocationIndex = index;
            $scope.chosenLocation = data[$scope.chosenLocationIndex];
            $scope.setLocation($scope.chosenLocation, $scope.chosenLocationIndex);
        };

        $scope.clearExpectedRoute = () => {
            if (currentExpectedRouteCB) {
                currentExpectedRouteCB();
            }
            if (currentInitialMarkerCB) {
                currentInitialMarkerCB();
            }
            if (currentPrevExpectedRouteCB) {
                currentPrevExpectedRouteCB();
            }
            if (circleCloseCB) {
                circleCloseCB();
            }
            $scope.chosenLocation = null;
            $scope.chosenLocationIndex = null;
        };

        $scope.showExpectedRoute = (index) => {
            let item = data[index];

            if (currentExpectedRouteCB) {
                currentExpectedRouteCB();
            }

            let decodedPath = google.maps.geometry.encoding.decodePath(
                item.driver.expected_driver_route
            );
            let line = new google.maps.Polyline({
                path: decodedPath,
                strokeOpacity: 0,
                icons: [{
                    icon: routeSymbol,
                    offset: '1px',
                    repeat: '20px'
                }],
                map: map
            });
            addCleanCallbacks(line);
            currentExpectedRouteCB = () => {line.setMap(null);};
        };

        $scope.showPrevExpectedRoute = (index) => {
            let item = data[index];
            if (item.bad_route_meta === null) {
                return;
            }
            if (currentPrevExpectedRouteCB) {
                currentPrevExpectedRouteCB();
            }
            let line = new google.maps.Polyline({
                path: item.bad_route_meta.expected_route,
                strokeOpacity: 0,
                icons: [{
                    icon: prevRouteSymbol,
                    offset: '1px',
                    repeat: '20px'
                }],
                map: map
            });
            addCleanCallbacks(line);

            let locMarker = new google.maps.Marker({
                position: item.bad_route_meta.expected_point.location,
                map: map,
                icon: 'https://maps.gstatic.com/intl/en_us/mapfiles/markers2/measle_blue.png',
            });
            addCleanCallbacks(locMarker);

            currentPrevExpectedRouteCB = () => {
                line.setMap(null);
                locMarker.setMap(null);
            };
        };

        $scope.setLocation = (item, i) => {
            if (currentWindowCloseCB) {
                currentWindowCloseCB();
            }
            currentWindowCloseCB = () => {
                $scope.clearExpectedRoute();
                if (shouldApply) {
                    $scope.$apply();
                }
            };
            console.log(item);

            let initialLocMarker = new google.maps.Marker({
                position: stringToCoordinates(item.coordinate.location),
                map: map,
                title: i.toString(),
                icon: icons_url.REAL_LOCATION,
            });
            currentInitialMarkerCB = addCleanCallbacks(initialLocMarker);

            let accuracyRadius = new google.maps.Circle({
                strokeColor: '#ff5503',
                strokeOpacity: 0.8,
                strokeWeight: 2,
                fillColor: '#ffc529',
                fillOpacity: 0.35,
                map: map,
                center: stringToCoordinates(item.coordinate.location),
                radius: item.coordinate.accuracy,
            });
            circleCloseCB = addCleanCallbacks(accuracyRadius);

            $scope.chosenLocation = item;
            $scope.chosenLocationIndex = i;
            if (shouldApply) {
                $scope.$apply();
            }
        };

        data.forEach((item, i) => {
            let line = new google.maps.Polyline({
                path: item.driver.current_path.path,
                strokeOpacity: 0,
                icons: [{
                    icon: lineSymbol,
                    offset: '0',
                    repeat: '20px'
                }],
                map: map
            });
            addCleanCallbacks(line);

            let locMarker = new google.maps.Marker({
                position: stringToCoordinates(item.improved_location || item.coordinate.location),
                map: map,
                title: i.toString(),
                icon: getLocationIcon(item),
            });
            addCleanCallbacks(locMarker);

            locMarker.addListener('click', function() {
                shouldApply = true;
                $scope.setLocation(item, i);
                shouldApply = false;
            });
        });
    };


    // Initialization
    this.init = function() {
        this.initMap();
    };

    $scope.loadFile = function() {
        let file = document.getElementById("file-input").files[0];

        const reader = new FileReader();
        reader.onload = (result) => {
            let data = JSON.parse(result.target.result);
            let drivers = {};
            data.forEach((order) => {
                if (drivers[order.driver.id] === undefined) {
                    drivers[order.driver.id] = new Driver(order.driver);
                }
                drivers[order.driver.id].orders.push(new Order(order));
            });
            for (let key in drivers) {
                $scope.drivers.push(drivers[key]);
            }
            $scope.$apply();
        };
        reader.readAsText(file);
    };

    this.initMap = function() {
        map = new google.maps.Map(document.getElementById('map'), {
            zoom: 17,
            center: {lat: 53.897422, lng: 27.470988}
        });
    };

    this.init();
});


let getLocationIcon = function(item) {
    let icon;
    if (!item.improved_location) {
        return icons_url.REAL_LOCATION;
    }
    if (item.requests === 0){
        if (item.coordinate.google_requests === 0) {
            icon = icons_url.SNAPPED_GOOD;
        } else {
            icon = icons_url.SNAPPED_CURRENTLY_NO_REQUESTS;
        }
    } else {
        icon = icons_url.SNAPPED_WITH_REQUESTS;
    }
    return icon;
};
