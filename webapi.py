from aiohttp import web

last_image = None

async def web_index(request):
    return web.Response(text = 'Hello Aiohttp!')

async def web_binary_image(request):
    if last_image is None:
        response = web.Response(
            status = 500,
            text = "Request failed"
        )
    else:
        response = web.Response(
            status = 200,
            content_type = 'text/plain',
            body = last_image
        )
    return response

async def web_resolution(request):
    width, height = camera.resolution

    response = web.Response(
        status = 200,
        text = "{}x{}".format(width, height)
    )
    return response

async def web_framerate(request):
    fr = float(camera.framerate)
    response = web.Response(
        status = 200,
        content_type = 'text/plain',
        text = str(fr)
    )
    return response

async def web_shutter_speed(request):
    sh = camera.shutter_speed
    response = web.Response(
        status = 200,
        content_type = 'text/plain',
        text = str(sh)
    )
    return response

async def web_exposure_mode(request):
    response = web.Response(
        status = 200,
        content_type = 'text/plain',
        text = camera.exposure_mode
    )
    return response

async def web_set_exposure_mode(request):
    try:
        camera.exposure_mode = await request.text()
        response = web.Response(
            status = 200
        )
        return response
    except Exception as e:
        logger.exception("Failed to set exposure mode")
        response = web.Response(
            status = 500,
            text = str(e)
        )
        return response

async def web_set_resolution(request):
    try:
        camera.resolution = await request.text()
        response = web.Response(
            status = 200
        )
        return response
    except Exception as e:
        logger.exception("Failed to set resolution")
        response = web.Response(
            status = 500,
            text = str(e)
        )
        return response

async def web_set_framerate(request):
    try:
        camera.framerate = await request.text()
        response = web.Response(
            status = 200
        )
        return response
    except Exception as e:
        logger.exception("Failed to set framerate")
        response = web.Response(
            status = 500,
            text = str(e)
        )
        return response


async def web_thing_description(request):
    host = platform.node()
    desc = {
        "name": host,
        "mac_address": get_local_mac(),
        "type": "camera",
        "description": "PiCamera",
        "properties": {
            "resolution": {
                "type": "string",
                "description": "The current camera resolution",
                "href": "/properties/resolution"
            },
            "framerate": {
                "type": "string",
                "description": "The current camera frame rate",
                "href": "/properties/framerate"
            },
            "shutterSpeed": {
                "type": "number",
                "description": "The current camera shutter speed",
                "href": "/properties/shutterSpeed"
            },
            "exposureMode": {
                "type": "string",
                "description": "The current camera exposure mode",
                "href": "/properties/exposureMode"
            }
        }
    }
    response = web.Response(
        status = 200,
        content_type = 'application/json',
        body = json.dumps(desc).encode('utf-8')
    )
    return response

async def web_loop():
    logger.info('Starting web loop...')

    app = web.Application()
    app.router.add_get('/', web_index)
    app.router.add_get('/webthing', web_thing_description)

    app.router.add_get('/properties/stillImage', web_binary_image)
    app.router.add_get('/properties/resolution', web_resolution)
    app.router.add_get('/properties/framerate', web_framerate)
    app.router.add_get('/properties/shutterSpeed', web_shutter_speed)
    app.router.add_get('/properties/exposureMode', web_exposure_mode)

    app.router.add_put('/properties/exposureMode', web_set_exposure_mode)
    app.router.add_put('/properties/resolution', web_set_resolution)
    app.router.add_put('/properties/framerate', web_set_framerate)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 80)
    await site.start()
