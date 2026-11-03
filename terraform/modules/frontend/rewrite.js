function handler(event) {
    if (typeof releaseExpiresAt !== 'undefined' && releaseExpiresAt > 0 &&
            Date.now() >= releaseExpiresAt * 1000) {
        return {statusCode: 403, statusDescription: 'Closed',
            headers: {'cache-control': {value: 'no-store'}}};
    }
    var request = event.request;
    var uri = request.uri;
    if (uri.endsWith('/')) {
        request.uri += 'index.html';
    } else if (uri.substring(uri.lastIndexOf('/') + 1).indexOf('.') === -1) {
        request.uri += '/index.html';
    }
    return request;
}
