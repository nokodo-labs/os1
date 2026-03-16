# PWA CDN asset setup

The backend compiles a PWA web app manifest at `GET /system/manifest.json`.
When `branding.public_cdn_origin` is set, the manifest references icons,
shortcut icons, and screenshots from a well-known directory tree on the CDN.

If the CDN origin is not configured, the manifest is still served but contains
no asset references - basic install still works, just without branded icons or
screenshots.

---

## CDN configuration

Set the CDN origin in settings (env or admin console):

```
NOKODO__BRANDING__PUBLIC_CDN_ORIGIN=https://cdn.example.com
```

All asset paths below are relative to this origin.

---

## required directory layout

```
{cdn}/static/os1/
├── icon-1024-maskable.png       - 1024x1024 px, PNG, maskable safe zone
├── icon-512-maskable.png        -  512x512  px, PNG, maskable safe zone
├── favicon.svg                  - square SVG favicon
├── shortcuts/
│   ├── notes-1024.png           - 1024x1024 px, PNG
│   ├── reminders-1024.png       - 1024x1024 px, PNG
│   ├── projects-1024.png        - 1024x1024 px, PNG
│   ├── library-1024.png         - 1024x1024 px, PNG
│   └── social-1024.png          - 1024x1024 px, PNG
└── screenshots/
    ├── narrow-1-1770x3835.png   \
    ├── narrow-2-1770x3835.png    |  mobile screenshots
    ├── narrow-3-1770x3835.png    |  1770x3835 px, PNG, form_factor: narrow
    ├── narrow-4-1770x3835.png    |
    ├── narrow-5-1770x3835.png   /
    ├── wide-1-3840x2160.png     \
    ├── wide-2-3840x2160.png      |
    ├── wide-3-3840x2160.png      |  desktop screenshots
    ├── wide-4-3840x2160.png      |  3840x2160 px, PNG, form_factor: wide
    ├── wide-5-3840x2160.png      |
    ├── wide-6-3840x2160.png      |
    ├── wide-7-3840x2160.png      |
    └── wide-8-3840x2160.png     /
```

---

## asset specs

### app icons

| file                     | size         | notes                                                       |
| ------------------------ | ------------ | ----------------------------------------------------------- |
| `icon-1024-maskable.png` | 1024x1024    | important content within the inner 80% (maskable safe zone) |
| `icon-512-maskable.png`  | 512x512      | same safe zone rule                                         |
| `favicon.svg`            | any (square) | used as `purpose: any maskable`; keep it simple and square  |

### shortcut icons

All shortcut icons: **1024x1024 px PNG**. These appear in the app install
prompt and long-press home screen menu on Android/Chrome. Keep them simple -
a single recognizable symbol on a transparent or solid background.

| file                           | shortcut     |
| ------------------------------ | ------------ |
| `shortcuts/notes-1024.png`     | `/notes`     |
| `shortcuts/reminders-1024.png` | `/reminders` |
| `shortcuts/projects-1024.png`  | `/projects`  |
| `shortcuts/library-1024.png`   | `/library`   |
| `shortcuts/social-1024.png`    | `/social`    |

### screenshots

Screenshots are shown in the install prompt on supported browsers.

| dimension | form factor     | count | naming                        |
| --------- | --------------- | ----- | ----------------------------- |
| 1770x3835 | narrow (mobile) | 5     | `narrow-{1..5}-1770x3835.png` |
| 3840x2160 | wide (desktop)  | 8     | `wide-{1..8}-3840x2160.png`   |

Capture at 2x device pixel ratio (actual pixel dimensions above). PNG only.

---

## CORS and caching

- Serve all files with `Access-Control-Allow-Origin: *` (required for browsers
  to load manifest-referenced resources cross-origin).
- Recommend `Cache-Control: public, max-age=31536000, immutable` for all assets
  (use content-hashed filenames or versioned paths if you need to rotate them).

---

## manifest cache invalidation

The compiled manifest is cached in-memory on the backend. It is automatically
invalidated whenever settings are updated via the admin API. If you update CDN
assets at the same paths without changing settings, restart the backend process
or trigger a settings PATCH to force recompilation.
