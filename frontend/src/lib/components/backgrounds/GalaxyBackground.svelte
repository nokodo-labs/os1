<script lang="ts">
    interface Props {
        className?: string
    }

    let { className = '' }: Props = $props()
</script>

<div class={`galaxy-css ${className}`.trim()}>
    <div class="nebula" aria-hidden="true"></div>
    <div class="starfield" aria-hidden="true"></div>
    <div class="starfield depth" aria-hidden="true"></div>
    <div class="glow" aria-hidden="true"></div>
</div>

<style>
    .galaxy-css {
        position: absolute;
        inset: 0;
        overflow: hidden;
        background: radial-gradient(circle at 50% 115%, rgba(6, 10, 24, 0.85), rgba(0, 0, 0, 0.98));
        filter: saturate(1.15) contrast(1.05);
    }

    .nebula {
        position: absolute;
        inset: -40%;
        background: radial-gradient(circle at 15% 45%, rgba(92, 106, 255, 0.28), transparent 60%);
        animation: nebulaDrift 32s ease-in-out infinite;
        transform-origin: center;
        filter: blur(36px);
        opacity: 0.8;
    }

    .starfield,
    .starfield.depth {
        position: absolute;
        inset: -10%;
        background-image:
            radial-gradient(1px 1px at 10% 12%, rgba(255, 255, 255, 0.6), transparent),
            radial-gradient(1px 1px at 80% 18%, rgba(180, 210, 255, 0.55), transparent),
            radial-gradient(1px 1px at 40% 70%, rgba(160, 190, 255, 0.7), transparent),
            radial-gradient(1px 1px at 65% 42%, rgba(130, 180, 255, 0.5), transparent),
            radial-gradient(1px 1px at 72% 78%, rgba(255, 255, 255, 0.65), transparent),
            radial-gradient(1px 1px at 25% 82%, rgba(170, 200, 255, 0.6), transparent);
        background-size: 200% 200%;
        animation: starParallax 60s linear infinite;
        opacity: 0.75;
    }

    .starfield.depth {
        mix-blend-mode: screen;
        animation-duration: 75s;
        opacity: 0.4;
        filter: blur(0.5px);
    }

    .glow {
        position: absolute;
        inset: -15%;
        background:
            radial-gradient(circle at 50% 25%, rgba(160, 200, 255, 0.18), transparent 65%),
            radial-gradient(circle at 50% 80%, rgba(90, 120, 255, 0.15), transparent 60%);
        animation: glowBreath 14s ease-in-out infinite;
        pointer-events: none;
    }

    @keyframes nebulaDrift {
        0% {
            transform: translate3d(-2%, 2%, 0) scale(1.04);
        }
        50% {
            transform: translate3d(3%, -1%, 0) scale(1.07);
        }
        100% {
            transform: translate3d(-2%, 2%, 0) scale(1.04);
        }
    }

    @keyframes starParallax {
        0% {
            background-position: 0% 0%;
        }
        50% {
            background-position: 50% 40%;
        }
        100% {
            background-position: 100% 100%;
        }
    }

    @keyframes glowBreath {
        0%,
        100% {
            opacity: 0.6;
        }
        50% {
            opacity: 0.85;
        }
    }
</style>
