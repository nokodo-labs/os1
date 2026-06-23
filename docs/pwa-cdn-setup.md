# PWA CDN asset setup

The backend compiles a PWA web app manifest at `GET /system/manifest.json`.
Leave `branding.pwa_manifest_url` blank to use it. Set that URL only when you
want to replace the whole generated manifest with a static file.

Each generated manifest asset has its own source setting:

| source     | behavior                                                                                           |
| ---------- | -------------------------------------------------------------------------------------------------- |
| `default`  | use the built-in nokodo URL, except shortcut icons which use the frontend `/shortcuts/*.png` files |
| `cdn`      | use the same well-known path under `branding.public_cdn_origin`, or default when no CDN is set     |
| `custom`   | use the asset's full custom URL                                                                    |
| `disabled` | omit that asset reference from the generated manifest                                              |

If `pwa_manifest_url` is set, these generated-manifest asset settings do not
change the external manifest file. Frontend media settings still apply to
non-manifest resources like the browser favicon and sidebar logo.

The generated manifest always uses absolute `start_url`, `scope`, shortcut URLs,
and default shortcut icon URLs. Set `branding.public_frontend_origin` explicitly
in production. When it is blank, the backend derives the frontend origin from
the API request host and the default frontend port `888`. If no request origin
is available, the API origin is assumed to be `http://localhost:1383`, so the
frontend origin becomes `http://localhost:888`.

## CDN origin

Set the CDN origin in settings when you want selected assets to use CDN-default:

```env
NOKODO__BRANDING__PUBLIC_CDN_ORIGIN=https://cdn.example.com
```

The CDN-default path root is:

```text
{cdn}/static/os1/
```

## Generated manifest asset paths

App icons:

| asset setting        | default URL                                            | CDN-default path                          |
| -------------------- | ------------------------------------------------------ | ----------------------------------------- |
| `icon_1024_maskable` | `https://nokodo.net/static/os1/icon-1024-maskable.png` | `{cdn}/static/os1/icon-1024-maskable.png` |
| `icon_512_any`       | `https://nokodo.net/static/os1/icon-512-any.png`       | `{cdn}/static/os1/icon-512-any.png`       |

`icon_1024_maskable` is emitted with manifest `purpose: maskable`.
`icon_512_any` is emitted with `purpose: any`. Browser favicons and Apple touch
icons are frontend media assets, not manifest icon entries.

Shortcut icons:

| asset setting        | default URL                          | CDN-default path                           | shortcut URL |
| -------------------- | ------------------------------------ | ------------------------------------------ | ------------ |
| `shortcut_notes`     | `{frontend}/shortcuts/notes.png`     | `{cdn}/static/os1/shortcuts/notes.png`     | `/notes`     |
| `shortcut_reminders` | `{frontend}/shortcuts/reminders.png` | `{cdn}/static/os1/shortcuts/reminders.png` | `/reminders` |
| `shortcut_calendar`  | `{frontend}/shortcuts/calendar.png`  | `{cdn}/static/os1/shortcuts/calendar.png`  | `/calendar`  |
| `shortcut_messages`  | `{frontend}/shortcuts/messages.png`  | `{cdn}/static/os1/shortcuts/messages.png`  | `/messages`  |
| `shortcut_projects`  | `{frontend}/shortcuts/projects.png`  | `{cdn}/static/os1/shortcuts/projects.png`  | `/projects`  |
| `shortcut_library`   | `{frontend}/shortcuts/library.png`   | `{cdn}/static/os1/shortcuts/library.png`   | `/library`   |
| `shortcut_social`    | `{frontend}/shortcuts/social.png`    | `{cdn}/static/os1/shortcuts/social.png`    | `/social`    |
| `shortcut_settings`  | `{frontend}/shortcuts/settings.png`  | `{cdn}/static/os1/shortcuts/settings.png`  | `/settings`  |

Screenshot assets:

| asset settings                                      | default URL pattern                                                     | CDN-default path pattern                                   |
| --------------------------------------------------- | ----------------------------------------------------------------------- | ---------------------------------------------------------- |
| `screenshot_narrow_1` through `screenshot_narrow_5` | `https://nokodo.net/static/os1/screenshots/narrow-{1..5}-1770x3835.png` | `{cdn}/static/os1/screenshots/narrow-{1..5}-1770x3835.png` |
| `screenshot_wide_1` through `screenshot_wide_8`     | `https://nokodo.net/static/os1/screenshots/wide-{1..8}-3840x2160.png`   | `{cdn}/static/os1/screenshots/wide-{1..8}-3840x2160.png`   |

## Asset specs

| file type                | size      | notes                                                          |
| ------------------------ | --------- | -------------------------------------------------------------- |
| maskable app icon PNG    | 1024x1024 | keep important content inside the inner 80% maskable safe zone |
| any-purpose app icon PNG | 512x512   | used for the manifest `any` icon and default Apple touch icon  |
| shortcut PNG             | 192x192   | transparent PNG recommended                                    |
| narrow screenshot PNG    | 1770x3835 | mobile install prompt screenshot                               |
| wide screenshot PNG      | 3840x2160 | desktop install prompt screenshot                              |

## Frontend media assets

Frontend media settings use the same source idea, without `disabled`:

| media asset      | default URL                                      | CDN-default path                    |
| ---------------- | ------------------------------------------------ | ----------------------------------- |
| favicon          | `https://nokodo.net/static/os1/favicon.svg`      | `{cdn}/static/os1/favicon.svg`      |
| Apple touch icon | `https://nokodo.net/static/os1/icon-512-any.png` | `{cdn}/static/os1/icon-512-any.png` |
| sidebar logo     | `https://nokodo.net/media/images/logo_full.svg`  | `{cdn}/static/os1/sidebar-logo.svg` |
| splash logo      | `https://nokodo.net/media/images/logo_full.svg`  | `{cdn}/static/os1/splash-logo.svg`  |

## CORS, MIME, and caching

- Serve CDN files with `Access-Control-Allow-Origin: *` when they are loaded
  cross-origin from the manifest.
- Serve static manifest overrides with `Content-Type: application/manifest+json`.
  Chrome can ignore a valid-looking manifest if it is served as plain JSON.
- Use long-lived caching for versioned assets, for example
  `Cache-Control: public, max-age=31536000, immutable`.

## Manifest cache invalidation

The compiled manifest is cached in memory on the backend and invalidated when
settings change through the admin API. If you replace CDN files at the same URL
without changing settings, restart the backend process or submit a no-op
settings PATCH to force recompilation.
