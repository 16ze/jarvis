# Ada Redesign v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refonte visuelle d'Ada : fond blanc global, visualizer sphère 3D de points bleus, hamburger menu central-bas avec boutons 3D glass, et animation d'ouverture des fenêtres — sans casser aucune fonctionnalité existante.

**Architecture:** Suit le spec `docs/superpowers/specs/2026-05-18-ada-redesign-design.md`. 4 commits indépendants : (1) PointCloudSphere remplace Visualizer ; (2) fond blanc + GlassButton + HamburgerMenu ; (3) refonte stylistique des 6 fenêtres modales ; (4) animations Framer Motion d'ouverture des fenêtres. Aucune logique métier touchée — uniquement composants visuels et classes Tailwind. Les fichiers obsolètes (`Visualizer.jsx`, `ToolsModule.jsx`) sont **conservés** pour rollback.

**Tech Stack:** React 18, Vite, Electron 28, Tailwind CSS 3.4, Three.js 0.160 via `@react-three/fiber` 8.15 + `drei` 9.99, framer-motion 11, lucide-react.

**Pas de test framework configuré** — chaque tâche se valide par exécution `npm run dev` et observation visuelle. Les critères d'acceptation §10 du spec servent de checklist finale.

**Branche cible :** `feat/ada-redesign-v3` (à créer depuis l'état courant avant d'attaquer la Task 1).

---

## Pré-requis : créer la branche de travail

### Task 0: Créer la branche dédiée

**Files:** aucun fichier modifié — opération git uniquement.

- [ ] **Step 1: Vérifier que `package.json` contient bien Three.js et framer-motion**

Run: `grep -E "three|framer-motion|@react-three" "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/package.json"`

Expected output (contains):
```
"@react-three/drei": "^9.99.0",
"@react-three/fiber": "^8.15.16",
"framer-motion": "^11.0.0",
"three": "^0.160.0"
```

- [ ] **Step 2: Stash les modifs en cours pour ne pas les emporter dans la nouvelle branche**

Run: `git -C "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis" stash push -u -m "wip-before-redesign-v3"`

Si rien à stash, message "No local changes to save" — c'est OK, continuer.

- [ ] **Step 3: Créer et basculer sur la nouvelle branche**

Run: `git -C "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis" checkout -b feat/ada-redesign-v3`

- [ ] **Step 4: Remettre le stash si applicable**

Run: `git -C "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis" stash list | head -1`

Si la liste contient `wip-before-redesign-v3`, executer `git -C "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis" stash pop`. Sinon ignorer.

- [ ] **Step 5: Vérifier l'état**

Run: `git -C "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis" status -sb`

Expected: branche `feat/ada-redesign-v3`, éventuelles modifs `backend/`, `brain/` (non liées au redesign) — c'est OK, on les laisse de côté.

---

## Commit 1 — PointCloudSphere remplace le canvas circle

### Task 1: Créer le composant PointCloudSphere

**Files:**
- Create: `src/components/PointCloudSphere.jsx`

- [ ] **Step 1: Créer le fichier avec la structure complète**

Path: `/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/src/components/PointCloudSphere.jsx`

Content:

```jsx
import React, { memo, useMemo, useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import * as THREE from 'three';

// Génère N positions uniformément réparties sur une sphère via Fibonacci.
const generateFibonacciSphere = (count, radius) => {
    const positions = new Float32Array(count * 3);
    const golden = Math.PI * (1 + Math.sqrt(5));
    for (let i = 0; i < count; i += 1) {
        const t = (i + 0.5) / count;
        const phi = Math.acos(1 - 2 * t);
        const theta = golden * (i + 0.5);
        positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
        positions[i * 3 + 1] = radius * Math.cos(phi);
        positions[i * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta);
    }
    return positions;
};

const COLOR_IDLE = new THREE.Color('#3b82f6');   // blue-500
const COLOR_ACTIVE = new THREE.Color('#2563eb'); // blue-600

const PointsCluster = ({ count, radius, isSpeaking, intensity, reduceMotion }) => {
    const pointsRef = useRef(null);
    const materialRef = useRef(null);

    const originalPositions = useMemo(
        () => generateFibonacciSphere(count, radius),
        [count, radius]
    );

    // Buffer mutable utilisé chaque frame ; cloné depuis original au démarrage.
    const livePositions = useMemo(() => originalPositions.slice(), [originalPositions]);

    const tmpColor = useMemo(() => new THREE.Color(), []);

    useFrame((state) => {
        const points = pointsRef.current;
        const material = materialRef.current;
        if (!points || !material) return;

        const t = state.clock.elapsedTime;

        // 1. Rotation
        const rotSpeed = isSpeaking ? 0.003 : 0.0008;
        points.rotation.y += reduceMotion ? rotSpeed * 0.3 : rotSpeed;

        // 2. Déplacement radial
        const positionsAttr = points.geometry.attributes.position;
        const arr = positionsAttr.array;
        const intensitySafe = Math.max(0, Math.min(1, intensity || 0));

        for (let i = 0; i < count; i += 1) {
            const ox = originalPositions[i * 3];
            const oy = originalPositions[i * 3 + 1];
            const oz = originalPositions[i * 3 + 2];

            let scale;
            if (isSpeaking && !reduceMotion) {
                const wobble = Math.sin(t * 8 + i * 0.1) * 0.3;
                scale = 1 + intensitySafe * 0.15 * (1 + wobble);
            } else {
                scale = 1 + Math.sin(t * 1.5) * 0.02;
            }

            arr[i * 3] = ox * scale;
            arr[i * 3 + 1] = oy * scale;
            arr[i * 3 + 2] = oz * scale;
        }
        positionsAttr.needsUpdate = true;

        // 3. Couleur lerp
        const targetColor = intensitySafe > 0.6 ? COLOR_ACTIVE : COLOR_IDLE;
        tmpColor.copy(material.color);
        tmpColor.lerp(targetColor, 0.05);
        material.color.copy(tmpColor);

        // 4. Taille des points
        const targetSize = isSpeaking ? 0.06 : 0.04;
        material.size = material.size + (targetSize - material.size) * 0.05;
    });

    return (
        <points ref={pointsRef}>
            <bufferGeometry>
                <bufferAttribute
                    attach="attributes-position"
                    count={count}
                    array={livePositions}
                    itemSize={3}
                />
            </bufferGeometry>
            <pointsMaterial
                ref={materialRef}
                color={COLOR_IDLE}
                size={0.04}
                sizeAttenuation
                transparent
                opacity={0.85}
                depthWrite={false}
            />
        </points>
    );
};

const PointCloudSphere = ({
    isSpeaking = false,
    intensity = 0,
    reduceMotion = false,
    width = 550,
    height = 350,
}) => {
    const pointCount = reduceMotion ? 1000 : 2000;
    const dpr = reduceMotion ? 1 : [1, 2];

    return (
        <div style={{ width, height }} className="relative">
            <Canvas
                dpr={dpr}
                camera={{ position: [0, 0, 3], fov: 50 }}
                gl={{ antialias: !reduceMotion, alpha: true }}
            >
                <ambientLight intensity={0.5} />
                <PointsCluster
                    count={pointCount}
                    radius={1.0}
                    isSpeaking={isSpeaking}
                    intensity={intensity}
                    reduceMotion={reduceMotion}
                />
            </Canvas>
        </div>
    );
};

export default memo(PointCloudSphere);
```

- [ ] **Step 2: Vérifier que le fichier compile (vite lance déjà en mode dev)**

Run: `cd "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis" && npx vite build --mode web 2>&1 | tail -20`

Expected: build réussit OU échoue uniquement sur `App.jsx` / autre fichier non lié. Aucune erreur dans `PointCloudSphere.jsx`. Si erreur dans le nouveau fichier, lire le message et corriger la syntaxe.

Note : le build complet peut échouer pour d'autres raisons non liées à ce composant — on cherche seulement à valider la compilation TS/JSX du nouveau fichier.

- [ ] **Step 3: Pas de commit encore — la substitution dans App.jsx vient juste après**

---

### Task 2: Substituer Visualizer par PointCloudSphere dans App.jsx

**Files:**
- Modify: `src/App.jsx` ligne 4 (import) et ligne 2061-2069 (usage)

- [ ] **Step 1: Ajouter l'import à côté de `Visualizer`**

Path: `/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/src/App.jsx`

Find line:
```jsx
import Visualizer from './components/Visualizer';
```

Replace with:
```jsx
import Visualizer from './components/Visualizer';
import PointCloudSphere from './components/PointCloudSphere';
```

- [ ] **Step 2: Remplacer l'usage du `<Visualizer>` central**

In `App.jsx`, find the block (around lines 2060-2070):

```jsx
                    <div className="relative z-20">
                        <Visualizer
                            audioData={aiAudioData}
                            audioDataRef={aiAudioDataRef}
                            isListening={isConnected && !isMuted}
                            intensity={isElectron ? null : audioAmp}
                            width={elementSizes.visualizer.w}
                            height={elementSizes.visualizer.h}
                            reduceMotion={isElectron}
                        />
                    </div>
```

Replace with:

```jsx
                    <div className="relative z-20">
                        <PointCloudSphere
                            isSpeaking={isConnected && !isMuted && (isElectron ? false : (audioAmp || 0) > 0.05)}
                            intensity={isElectron ? 0 : (audioAmp || 0)}
                            width={elementSizes.visualizer.w}
                            height={elementSizes.visualizer.h}
                            reduceMotion={isElectron}
                        />
                    </div>
```

Note : on garde `Visualizer` importé pour fallback (suppression dans un commit ultérieur après stabilisation).

- [ ] **Step 3: Lancer le projet en dev mode et vérifier visuellement**

Run: `cd "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis" && npm run dev`

(commande longue — laisser tourner dans un terminal séparé OU exécuter `npm run web` pour ne pas avoir Electron)

Open browser at `http://localhost:5173` (mode web). Vérifier :
- ✅ La page charge sans erreur console rouge
- ✅ Au centre, une sphère de points bleus est visible et tourne lentement
- ✅ La sphère reste visible (pas écran noir, pas écran blanc)

Si erreur console mentionnant `useFrame` ou `Canvas` → s'assurer que le composant est bien à l'intérieur d'un `<Canvas>` (il l'est dans le code ci-dessus). Si erreur React 18 sur Concurrent rendering → ignorer (warning non-bloquant).

- [ ] **Step 4: Tester la pulsation audio (manuel)**

Dans le navigateur ouvert : autoriser l'accès au micro, parler. La sphère doit pulser visiblement (les points s'écartent du centre) quand on parle.

Si pas de pulsation : ouvrir devtools, vérifier que `audioAmp` (variable App.jsx) est non-nul quand on parle. Si oui mais pas de pulsation → debug le prop `intensity` du composant.

- [ ] **Step 5: Stopper le dev server et commit**

```bash
cd "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis"
git add src/components/PointCloudSphere.jsx src/App.jsx
git commit -m "feat(visualizer): 3D point cloud sphere replaces canvas circle

PointCloudSphere : ~2000 points bleus en distribution Fibonacci sur sphère,
rotation lente continue, pulsation radiale + accélération + lerp couleur
vers blue-600 quand Ada parle. Performant via mutation directe du
BufferAttribute (un seul draw call).

Visualizer.jsx conservé pour rollback rapide.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Commit 2 — Fond blanc + GlassButton + HamburgerMenu

### Task 3: Bascule le fond global en blanc + ajout des tokens CSS

**Files:**
- Modify: `src/index.css` (entier)

- [ ] **Step 1: Lire le fichier actuel pour ne rien perdre**

Path: `/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/src/index.css`

Confirmer son contenu (61 lignes, fond noir + classes utilitaires + overrides Electron performance).

- [ ] **Step 2: Modifier la ligne `background-color: #000`**

Find:
```css
body {
  margin: 0;
  background-color: #000;
  overflow: hidden;
}
```

Replace with:
```css
:root {
  --ada-blue-accent: #3b82f6;
  --ada-blue-strong: #2563eb;
  --ada-blue-soft: #dbeafe;
  --ada-glass-bg: rgba(255, 255, 255, 0.6);
  --ada-glass-border: rgba(59, 130, 246, 0.4);
  --ada-glass-glow: rgba(59, 130, 246, 0.15);
}

body {
  margin: 0;
  background-color: #ffffff;
  color: #1e293b;
  overflow: hidden;
}
```

- [ ] **Step 3: Vérifier que les overrides electron-performance existants restent en bas du fichier**

Le bloc `.electron-performance .backdrop-blur, ...` (lignes 35-61 originelles) reste intouché.

- [ ] **Step 4: Vérification visuelle**

Run dev server : `npm run web`

Open `http://localhost:5173`. La fenêtre doit maintenant avoir un fond blanc. Beaucoup de texte cyan deviendra peu lisible — c'est attendu, l'audit cyan→bleu/sombre arrive dans la Task 7.

- [ ] **Step 5: Pas de commit pour l'instant — on enchaîne avec GlassButton**

---

### Task 4: Créer le composant GlassButton

**Files:**
- Create: `src/components/GlassButton.jsx`

- [ ] **Step 1: Créer le fichier**

Path: `/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/src/components/GlassButton.jsx`

Content:

```jsx
import React from 'react';
import { motion } from 'framer-motion';

// Map d'accent → classes Tailwind concrètes (utilisé par les 9 boutons d'outils).
const ACCENT_PRESETS = {
    blue: {
        idleText: 'text-blue-600',
        activeBg: 'bg-blue-500',
        activeText: 'text-white',
        glow: 'shadow-[0_8px_32px_rgba(59,130,246,0.18)]',
        glowHover: 'shadow-[0_12px_40px_rgba(59,130,246,0.30)]',
        border: 'border-blue-400/40',
        borderActive: 'border-blue-300/80',
    },
    green: {
        idleText: 'text-green-600',
        activeBg: 'bg-green-500',
        activeText: 'text-white',
        glow: 'shadow-[0_8px_32px_rgba(34,197,94,0.18)]',
        glowHover: 'shadow-[0_12px_40px_rgba(34,197,94,0.30)]',
        border: 'border-green-400/40',
        borderActive: 'border-green-300/80',
    },
    red: {
        idleText: 'text-red-600',
        activeBg: 'bg-red-500',
        activeText: 'text-white',
        glow: 'shadow-[0_8px_32px_rgba(239,68,68,0.18)]',
        glowHover: 'shadow-[0_12px_40px_rgba(239,68,68,0.30)]',
        border: 'border-red-400/40',
        borderActive: 'border-red-300/80',
    },
    purple: {
        idleText: 'text-purple-600',
        activeBg: 'bg-purple-500',
        activeText: 'text-white',
        glow: 'shadow-[0_8px_32px_rgba(168,85,247,0.18)]',
        glowHover: 'shadow-[0_12px_40px_rgba(168,85,247,0.30)]',
        border: 'border-purple-400/40',
        borderActive: 'border-purple-300/80',
    },
    orange: {
        idleText: 'text-orange-600',
        activeBg: 'bg-orange-500',
        activeText: 'text-white',
        glow: 'shadow-[0_8px_32px_rgba(249,115,22,0.18)]',
        glowHover: 'shadow-[0_12px_40px_rgba(249,115,22,0.30)]',
        border: 'border-orange-400/40',
        borderActive: 'border-orange-300/80',
    },
    yellow: {
        idleText: 'text-yellow-600',
        activeBg: 'bg-yellow-400',
        activeText: 'text-slate-900',
        glow: 'shadow-[0_8px_32px_rgba(253,224,71,0.25)]',
        glowHover: 'shadow-[0_12px_40px_rgba(253,224,71,0.40)]',
        border: 'border-yellow-400/50',
        borderActive: 'border-yellow-300/90',
    },
    cyan: {
        idleText: 'text-cyan-600',
        activeBg: 'bg-cyan-500',
        activeText: 'text-white',
        glow: 'shadow-[0_8px_32px_rgba(34,211,238,0.18)]',
        glowHover: 'shadow-[0_12px_40px_rgba(34,211,238,0.30)]',
        border: 'border-cyan-400/40',
        borderActive: 'border-cyan-300/80',
    },
    emerald: {
        idleText: 'text-emerald-600',
        activeBg: 'bg-emerald-500',
        activeText: 'text-white',
        glow: 'shadow-[0_8px_32px_rgba(52,211,153,0.18)]',
        glowHover: 'shadow-[0_12px_40px_rgba(52,211,153,0.30)]',
        border: 'border-emerald-400/40',
        borderActive: 'border-emerald-300/80',
    },
    violet: {
        idleText: 'text-violet-600',
        activeBg: 'bg-violet-500',
        activeText: 'text-white',
        glow: 'shadow-[0_8px_32px_rgba(139,92,246,0.18)]',
        glowHover: 'shadow-[0_12px_40px_rgba(139,92,246,0.30)]',
        border: 'border-violet-400/40',
        borderActive: 'border-violet-300/80',
    },
};

const GlassButton = ({
    icon,
    isActive = false,
    accentColor = 'blue',
    disabled = false,
    onClick,
    title,
    ariaLabel,
    size = 'md',
}) => {
    const preset = ACCENT_PRESETS[accentColor] || ACCENT_PRESETS.blue;
    const padding = size === 'lg' ? 'p-4' : 'p-3';

    const baseClasses = [
        'relative rounded-full overflow-hidden',
        'transition-all duration-200',
        padding,
        'border',
        isActive ? preset.borderActive : preset.border,
        'backdrop-blur-xl backdrop-saturate-150',
        isActive ? preset.activeBg : 'bg-gradient-to-br from-white/70 to-white/40',
        isActive ? preset.activeText : preset.idleText,
        'shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]',
        isActive ? preset.glowHover : preset.glow,
        disabled ? 'opacity-40 pointer-events-none' : 'cursor-pointer',
    ].join(' ');

    return (
        <motion.button
            type="button"
            onClick={disabled ? undefined : onClick}
            disabled={disabled}
            title={title}
            aria-label={ariaLabel || title}
            whileHover={disabled ? {} : { y: -2 }}
            whileTap={disabled ? {} : { y: 0, scale: 0.96 }}
            transition={{ type: 'spring', stiffness: 400, damping: 25 }}
            className={baseClasses}
        >
            {/* Reflet diagonal — désactivé en mode electron-performance via CSS body class */}
            <span
                className="absolute inset-0 pointer-events-none rounded-full glass-reflet"
                aria-hidden="true"
            />
            <span className="relative z-10 flex items-center justify-center">
                {icon}
            </span>
        </motion.button>
    );
};

export default GlassButton;
```

- [ ] **Step 2: Ajouter la classe CSS `.glass-reflet` dans `index.css`**

Path: `/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/src/index.css`

Find:
```css
.animate-fade-in {
  animation: fadeIn 0.3s ease-out forwards;
}
```

Add immediately after:

```css
.glass-reflet {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.55) 0%, rgba(255, 255, 255, 0) 50%);
}

.electron-performance .glass-reflet {
  display: none;
}
```

- [ ] **Step 3: Vérifier la compilation**

Pas de visuel à tester (composant pas encore utilisé) — juste s'assurer qu'aucune erreur d'import n'apparait :

Run: `cd "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis" && npx vite build --mode web 2>&1 | tail -15`

Le build doit se faire sans erreur **sur ce nouveau fichier**. Autres erreurs ignorables (composant pas encore référencé).

- [ ] **Step 4: Pas de commit — on enchaîne avec HamburgerMenu**

---

### Task 5: Créer le composant HamburgerMenu

**Files:**
- Create: `src/components/HamburgerMenu.jsx`

- [ ] **Step 1: Créer le fichier**

Path: `/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/src/components/HamburgerMenu.jsx`

Content:

```jsx
import React, { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
    Mic, MicOff, Settings, Power, Video, VideoOff,
    Hand, Lightbulb, Printer, Box, Monitor, BookOpen,
} from 'lucide-react';
import GlassButton from './GlassButton';

// Icône hamburger 2-traits qui morph en X via SVG + rotations.
const HamburgerIcon = ({ isOpen }) => (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
        <motion.line
            x1="4" y1="9" x2="20" y2="9"
            animate={isOpen ? { rotate: 45, y: 3, x: 0 } : { rotate: 0, y: 0, x: 0 }}
            style={{ originX: '12px', originY: '9px' }}
            transition={{ type: 'spring', stiffness: 300, damping: 22 }}
        />
        <motion.line
            x1="4" y1="15" x2="20" y2="15"
            animate={isOpen ? { rotate: -45, y: -3, x: 0 } : { rotate: 0, y: 0, x: 0 }}
            style={{ originX: '12px', originY: '15px' }}
            transition={{ type: 'spring', stiffness: 300, damping: 22 }}
        />
    </svg>
);

const HamburgerMenu = ({
    isConnected,
    isMuted,
    isVideoOn,
    isHandTrackingEnabled,
    showSettings,
    onTogglePower,
    onToggleMute,
    onToggleVideo,
    onToggleSettings,
    onToggleHand,
    onToggleKasa,
    showKasaWindow,
    onTogglePrinter,
    showPrinterWindow,
    onToggleCad,
    showCadWindow,
    isScreenMode,
    onToggleScreenMode,
    onToggleDocuments,
    activeDragElement,
    position,
    onMouseDown,
}) => {
    const [isOpen, setIsOpen] = useState(false);

    // Liste déclarative des 9 boutons d'outils — ordre identique à ToolsModule actuel.
    const tools = [
        {
            id: 'power',
            icon: <Power size={22} />,
            isActive: isConnected,
            accent: 'green',
            onClick: onTogglePower,
            title: 'Power',
        },
        {
            id: 'mic',
            icon: isMuted ? <MicOff size={22} /> : <Mic size={22} />,
            isActive: !isMuted && isConnected,
            accent: isMuted ? 'red' : 'cyan',
            disabled: !isConnected,
            onClick: onToggleMute,
            title: isMuted ? 'Unmute' : 'Mute',
        },
        {
            id: 'video',
            icon: isVideoOn ? <Video size={22} /> : <VideoOff size={22} />,
            isActive: isVideoOn,
            accent: 'purple',
            onClick: onToggleVideo,
            title: isVideoOn ? 'Disable video' : 'Enable video',
        },
        {
            id: 'settings',
            icon: <Settings size={22} />,
            isActive: showSettings,
            accent: 'cyan',
            onClick: onToggleSettings,
            title: 'Settings',
        },
        {
            id: 'hand',
            icon: <Hand size={22} />,
            isActive: isHandTrackingEnabled,
            accent: 'orange',
            onClick: onToggleHand,
            title: 'Hand tracking',
        },
        {
            id: 'kasa',
            icon: <Lightbulb size={22} />,
            isActive: showKasaWindow,
            accent: 'yellow',
            onClick: onToggleKasa,
            title: 'Smart devices',
        },
        {
            id: 'printer',
            icon: <Printer size={22} />,
            isActive: showPrinterWindow,
            accent: 'green',
            onClick: onTogglePrinter,
            title: '3D printers',
        },
        {
            id: 'cad',
            icon: <Box size={22} />,
            isActive: showCadWindow,
            accent: 'cyan',
            onClick: onToggleCad,
            title: 'CAD agent',
        },
        {
            id: 'screen',
            icon: <Monitor size={22} />,
            isActive: isScreenMode,
            accent: 'emerald',
            onClick: onToggleScreenMode,
            title: 'Screen mode',
        },
        {
            id: 'documents',
            icon: <BookOpen size={22} />,
            isActive: false,
            accent: 'violet',
            onClick: onToggleDocuments,
            title: 'Documents',
        },
    ];

    return (
        <div
            id="tools"
            onMouseDown={onMouseDown}
            className="absolute flex flex-col items-center gap-3 pointer-events-auto"
            style={{
                left: position.x,
                top: position.y,
                transform: 'translate(-50%, -50%)',
            }}
        >
            <AnimatePresence>
                {isOpen && (
                    <motion.div
                        key="tools-row"
                        initial={{ opacity: 0, y: 20 }}
                        animate={{
                            opacity: 1,
                            y: 0,
                            transition: { staggerChildren: 0.03, type: 'spring', stiffness: 300, damping: 24 },
                        }}
                        exit={{ opacity: 0, y: 10, transition: { duration: 0.15 } }}
                        className="flex flex-wrap justify-center gap-3 max-w-[640px]"
                    >
                        {tools.map((tool) => (
                            <motion.div
                                key={tool.id}
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0 }}
                            >
                                <GlassButton
                                    icon={tool.icon}
                                    isActive={tool.isActive}
                                    accentColor={tool.accent}
                                    disabled={tool.disabled}
                                    onClick={tool.onClick}
                                    title={tool.title}
                                />
                            </motion.div>
                        ))}
                    </motion.div>
                )}
            </AnimatePresence>

            <GlassButton
                icon={<HamburgerIcon isOpen={isOpen} />}
                isActive={isOpen}
                accentColor="blue"
                onClick={() => setIsOpen(!isOpen)}
                title={isOpen ? 'Fermer' : 'Ouvrir le menu'}
                ariaLabel="Menu"
                size="lg"
            />
        </div>
    );
};

export default HamburgerMenu;
```

- [ ] **Step 2: Vérifier la compilation isolée**

Run: `cd "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis" && npx vite build --mode web 2>&1 | tail -15`

Aucune erreur sur ce fichier. Autres erreurs ignorables.

- [ ] **Step 3: Pas de commit — on enchaîne avec la substitution dans App.jsx**

---

### Task 6: Substituer ToolsModule par HamburgerMenu dans App.jsx

**Files:**
- Modify: `src/App.jsx` ligne 9 (import) et lignes 2228-2265 (usage)

- [ ] **Step 1: Ajouter l'import**

Path: `/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/src/App.jsx`

Find:
```jsx
import ToolsModule from './components/ToolsModule';
```

Replace with:
```jsx
import ToolsModule from './components/ToolsModule';
import HamburgerMenu from './components/HamburgerMenu';
```

- [ ] **Step 2: Remplacer l'élément JSX rendu**

In `App.jsx`, find the block around lines 2227-2265 :

```jsx
                {/* Footer Controls / Tools Module */}
                <div className="z-20 flex justify-center pb-10 pointer-events-none">
                    <ToolsModule
                        isConnected={isConnected}
                        isMuted={isMuted}
                        ...
                        position={elementPositions.tools}
                        onMouseDown={(e) => handleMouseDown(e, 'tools')}
                    />
                </div>
```

Replace with:

```jsx
                {/* Footer Controls / Hamburger Menu */}
                <div className="z-20 flex justify-center pb-10 pointer-events-none">
                    <HamburgerMenu
                        isConnected={isConnected}
                        isMuted={isMuted}
                        isVideoOn={isVideoOn}
                        isHandTrackingEnabled={isHandTrackingEnabled}
                        showSettings={showSettings}
                        onTogglePower={togglePower}
                        onToggleMute={toggleMute}
                        onToggleVideo={toggleVideo}
                        onToggleSettings={() => setShowSettings(!showSettings)}
                        onToggleHand={() => {
                            const enabling = !isHandTrackingEnabled;
                            setIsHandTrackingEnabled(enabling);
                            if (socket.connected) {
                                socket.emit('hand_control_toggle', { enabled: enabling });
                            }
                            if (enabling && !isVideoOn) {
                                startVideo();
                            }
                            if (enabling) {
                                ensureHandLandmarker();
                            }
                        }}
                        onToggleKasa={toggleKasaWindow}
                        showKasaWindow={showKasaWindow}
                        onTogglePrinter={togglePrinterWindow}
                        showPrinterWindow={showPrinterWindow}
                        onToggleCad={() => setShowCadWindow(!showCadWindow)}
                        showCadWindow={showCadWindow}
                        isScreenMode={isScreenMode}
                        onToggleScreenMode={toggleScreenMode}
                        onToggleDocuments={() => setShowDocumentsWindow(true)}
                        activeDragElement={activeDragElement}
                        position={elementPositions.tools}
                        onMouseDown={(e) => handleMouseDown(e, 'tools')}
                    />
                </div>
```

- [ ] **Step 3: Vérification visuelle (dev server)**

Run: `npm run web` (ou `npm run dev` pour electron)

Open `http://localhost:5173`. Vérifier :
- ✅ Un bouton rond avec l'icône hamburger (≡, 2 traits) apparaît au centre-bas
- ✅ Cliquer dessus : les 9 boutons d'outils apparaissent en éventail au-dessus, animés (stagger)
- ✅ Re-cliquer : ils disparaissent, l'icône hamburger morph en × et revient en ≡
- ✅ Cliquer un bouton dans le menu (ex: Settings) : son état change visuellement (couleur active)
- ✅ Le visualizer (sphère 3D) reste centré et fonctionnel

Si l'éventail dépasse l'écran à droite/gauche : c'est attendu sur écrans étroits — `flex-wrap` gère le retour à la ligne automatiquement.

- [ ] **Step 4: Pas de commit — on enchaîne avec l'audit cyan→bleu/sombre**

---

### Task 7: Audit et bascule des couleurs cyan→bleu/sombre dans App.jsx

**Files:**
- Modify: `src/App.jsx` (multiples endroits identifiés par grep)

- [ ] **Step 1: Lister tous les usages cyan dans App.jsx**

Run: `cd "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis" && grep -n "text-cyan\|border-cyan\|bg-cyan\|from-cyan\|to-cyan\|shadow-\[.*cyan\|drop-shadow-\[.*cyan" src/App.jsx | head -80`

Garder la sortie dans un fichier temporaire pour cocher chaque ligne :

Run: `grep -n "text-cyan\|border-cyan\|bg-cyan\|from-cyan\|to-cyan\|shadow-\[.*cyan\|drop-shadow-\[.*cyan" src/App.jsx > /tmp/cyan-audit.txt`

- [ ] **Step 2: Pour chaque ligne du résultat, décider individuellement**

Règle de décision :
- Si l'élément est **dans la zone visible en permanence sur fond blanc** (top bar, project label, status bars, clock, mic level) → bascule vers du sombre/bleu :
  - `text-cyan-100` / `text-cyan-200` / `text-cyan-300` → `text-blue-600` ou `text-slate-700`
  - `text-cyan-500` → `text-blue-600`
  - `text-cyan-700` (foncé déjà) → `text-slate-500`
  - `border-cyan-500/20` → `border-blue-400/30`
  - `border-cyan-500/30` → `border-blue-400/40`
  - `bg-cyan-900/50` (hover) → `bg-blue-100`
- Si l'élément est **dans une fenêtre modale** (Cad, Terminal, Kasa, etc.) → ne pas toucher ici, traité au Commit 3.
- Si l'élément est **inactif/désactivé** (`text-cyan-900` pour "off") → bascule vers `text-slate-300` (gris clair).

- [ ] **Step 3: Modifier les classes une par une dans App.jsx — exemples concrets des principaux blocs**

**Top bar (lignes ~1965-2038) — fond blanc, donc rendre lisible :**

Find:
```jsx
<div className="h-12 bg-black/95 backdrop-blur-md border-b border-cyan-500/20 flex items-center justify-between relative z-50"
```

Replace with:
```jsx
<div className="h-12 bg-white/95 backdrop-blur-md border-b border-blue-400/30 flex items-center justify-between relative z-50"
```

**Project label flottant (ligne ~2076) :**

Find:
```jsx
<div className="absolute top-[70px] left-1/2 -translate-x-1/2 text-cyan-500 text-xs font-mono tracking-widest pointer-events-none z-50 bg-black/50 px-2 py-1 rounded backdrop-blur-sm border border-cyan-500/20">
```

Replace with:
```jsx
<div className="absolute top-[70px] left-1/2 -translate-x-1/2 text-blue-700 text-xs font-mono tracking-widest pointer-events-none z-50 bg-white/70 px-2 py-1 rounded backdrop-blur-sm border border-blue-400/30">
```

**Clock dans top bar (ligne ~2025) :**

Find:
```jsx
<div className="flex items-center gap-1.5 text-[11px] text-cyan-300/70 font-mono px-2">
    <Clock size={12} className="text-cyan-500/50" />
```

Replace with:
```jsx
<div className="flex items-center gap-1.5 text-[11px] text-slate-600 font-mono px-2">
    <Clock size={12} className="text-blue-500/70" />
```

**Window control buttons (lignes ~2029-2037) :**

Find:
```jsx
<button onClick={handleMinimize} className="p-1 hover:bg-cyan-900/50 rounded text-cyan-500 transition-colors">
    <Minus size={18} />
</button>
<button onClick={handleMaximize} className="p-1 hover:bg-cyan-900/50 rounded text-cyan-500 transition-colors">
    <div className="w-[14px] h-[14px] border-2 border-current rounded-[2px]" />
</button>
```

Replace with:
```jsx
<button onClick={handleMinimize} className="p-1 hover:bg-blue-100 rounded text-blue-600 transition-colors">
    <Minus size={18} />
</button>
<button onClick={handleMaximize} className="p-1 hover:bg-blue-100 rounded text-blue-600 transition-colors">
    <div className="w-[14px] h-[14px] border-2 border-current rounded-[2px]" />
</button>
```

**Visualizer container (lignes ~2044-2058) — il a un fond `bg-black/30`, on garde car ça crée un halo doux sur fond blanc, MAIS on adoucit la bordure :**

Find:
```jsx
                <div
                    id="visualizer"
                    className={`absolute flex items-center justify-center transition-all duration-200 
                        backdrop-blur-xl bg-black/30 border border-white/10 shadow-2xl overflow-visible
                        ${isModularMode ? (activeDragElement === 'visualizer' ? 'ring-2 ring-green-500 bg-green-500/10' : 'ring-1 ring-yellow-500/30 bg-yellow-500/5') + ' rounded-2xl pointer-events-auto' : 'rounded-2xl pointer-events-none'}
                    `}
```

Replace with:
```jsx
                <div
                    id="visualizer"
                    className={`absolute flex items-center justify-center transition-all duration-200 
                        backdrop-blur-xl bg-white/40 border border-blue-400/30 shadow-2xl overflow-visible
                        ${isModularMode ? (activeDragElement === 'visualizer' ? 'ring-2 ring-green-500 bg-green-500/10' : 'ring-1 ring-yellow-500/30 bg-yellow-500/5') + ' rounded-2xl pointer-events-auto' : 'rounded-2xl pointer-events-none'}
                    `}
```

Note : `bg-white/40` est un glass blanc translucide qui laisse passer le fond mais crée un halo doux autour de la sphère.

- [ ] **Step 4: Lister à nouveau les classes cyan restantes et nettoyer**

Run: `grep -cn "text-cyan\|border-cyan\|bg-cyan" "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/src/App.jsx"`

Le compteur final doit être ≤ 10 (les restes acceptables sont ceux qui s'affichent SUR un fond noir conservé : statut bars `bg-black/`, hand cursor overlays, etc.).

Pour chaque occurrence restante, vérifier qu'elle est **sur un fond sombre** (sinon, basculer).

- [ ] **Step 5: Test visuel global**

Run: `npm run web`

Open `http://localhost:5173`. Vérifier :
- ✅ Top bar est lisible : texte sombre/bleu sur fond blanc/cyan-soft, pas de "cyan invisible"
- ✅ Project label est lisible
- ✅ Clock et boutons fenêtre (minimize/maximize/close) sont visibles et cliquables
- ✅ Le visualizer 3D est centré dans un halo blanc doux
- ✅ Le hamburger menu fonctionne

- [ ] **Step 6: Commit du Commit 2**

```bash
cd "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis"
git add src/index.css src/components/GlassButton.jsx src/components/HamburgerMenu.jsx src/App.jsx
git commit -m "feat(ui): white background + hamburger menu + 3D glass buttons

- Fond blanc global (index.css) + tokens CSS pour les bleus
- GlassButton.jsx : bouton 3D glass paramétrable avec 9 accents
- HamburgerMenu.jsx : icône 2-traits qui morph en X, déroule les 9 boutons
  d'outils avec stagger
- App.jsx : substitue ToolsModule → HamburgerMenu, audit cyan → bleu/sombre
  sur top bar, project label, clock, window controls, visualizer container
- ToolsModule.jsx conservé pour rollback

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Commit 3 — Fenêtres modales en glass blanc translucide

### Task 8: Refondre CadWindow

**Files:**
- Modify: `src/App.jsx` lignes ~2141-2182 (le wrapping de CadWindow)
- Modify: `src/components/CadWindow.jsx` (header + contenu si classes cyan)

- [ ] **Step 1: Lire le CadWindow.jsx actuel**

Run: `wc -l "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/src/components/CadWindow.jsx"` puis le Read le fichier en entier.

- [ ] **Step 2: Modifier le wrapping dans App.jsx**

Find (App.jsx lignes ~2141-2147):
```jsx
                    <div
                        id="cad"
                        className={`absolute flex flex-col transition-all duration-200 
                        backdrop-blur-xl bg-black/40 border border-white/10 shadow-2xl overflow-hidden rounded-2xl
                        ${activeDragElement === 'cad' ? 'ring-2 ring-green-500 bg-green-500/10' : ''}
                    `}
```

Replace with:
```jsx
                    <div
                        id="cad"
                        className={`absolute flex flex-col transition-all duration-200 
                        backdrop-blur-xl bg-white/70 border border-blue-400/40 shadow-2xl overflow-hidden rounded-2xl
                        ${activeDragElement === 'cad' ? 'ring-2 ring-blue-500 bg-blue-500/10' : ''}
                    `}
```

- [ ] **Step 3: Modifier le drag handle (header) de la fenêtre Cad (App.jsx ligne ~2158-2170)**

Find:
```jsx
                        <div
                            data-drag-handle
                            className="h-8 bg-gray-900/80 border-b border-cyan-500/20 flex items-center justify-between px-3 cursor-grab active:cursor-grabbing shrink-0"
                        >
                            <span className="text-xs font-bold tracking-widest text-cyan-500/70">CAD PROTOTYPE</span>
                            <button
                                onClick={() => setShowCadWindow(false)}
                                className="text-gray-400 hover:text-red-400 hover:bg-red-500/20 p-1 rounded transition-colors"
                            >
                                ✕
                            </button>
                        </div>
```

Replace with:
```jsx
                        <div
                            data-drag-handle
                            className="h-8 bg-white/60 border-b border-blue-400/30 flex items-center justify-between px-3 cursor-grab active:cursor-grabbing shrink-0"
                        >
                            <span className="text-xs font-bold tracking-widest text-blue-700">CAD PROTOTYPE</span>
                            <button
                                onClick={() => setShowCadWindow(false)}
                                className="text-slate-500 hover:text-red-500 hover:bg-red-50 p-1 rounded transition-colors"
                            >
                                ✕
                            </button>
                        </div>
```

- [ ] **Step 4: Auditer le contenu de `CadWindow.jsx` (pas App.jsx)**

Run: `grep -n "text-cyan\|border-cyan\|bg-cyan\|text-gray-\|bg-gray-\|bg-black" "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/src/components/CadWindow.jsx"`

Pour chaque match, appliquer la même règle qu'en Task 7 :
- `text-cyan-*` → `text-blue-600` ou `text-slate-700`
- `border-cyan-500/X` → `border-blue-400/X`
- `bg-gray-900` → `bg-white/80`
- `bg-black/X` → `bg-white/X` avec opacité conservée
- `text-gray-300` / `text-gray-400` → `text-slate-700` / `text-slate-500`

Faire les substitutions une par une. Ne pas toucher la logique (handlers, refs, état).

- [ ] **Step 5: Test visuel**

Run: `npm run web`

Open `http://localhost:5173`, cliquer le hamburger, cliquer l'icône CAD. La fenêtre CAD doit apparaître avec :
- ✅ Fond glass blanc translucide
- ✅ Bordure bleue
- ✅ Header lisible "CAD PROTOTYPE" en bleu
- ✅ Bouton X de fermeture visible
- ✅ Contenu interne lisible (pas de texte cyan invisible)

- [ ] **Step 6: Pas de commit — on enchaîne avec les autres fenêtres**

---

### Task 9: Refondre TerminalWindow

**Files:**
- Modify: `src/App.jsx` lignes ~2186-2211 (le wrapping)
- Modify: `src/components/TerminalWindow.jsx` (header glass blanc, pane console reste sombre)

- [ ] **Step 1: Lire TerminalWindow.jsx**

Read `/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/src/components/TerminalWindow.jsx`.

- [ ] **Step 2: Modifier le wrapping dans App.jsx**

Find (App.jsx lignes ~2188-2203):
```jsx
                    <div
                        id="terminal"
                        className={`absolute flex flex-col transition-all duration-200
                        backdrop-blur-xl bg-black/40 border border-white/10 shadow-2xl overflow-hidden rounded-lg
                        ${activeDragElement === 'terminal' ? 'ring-2 ring-green-500 bg-green-500/10' : ''}
                    `}
```

Replace with:
```jsx
                    <div
                        id="terminal"
                        className={`absolute flex flex-col transition-all duration-200
                        backdrop-blur-xl bg-white/70 border border-blue-400/40 shadow-2xl overflow-hidden rounded-lg
                        ${activeDragElement === 'terminal' ? 'ring-2 ring-blue-500 bg-blue-500/10' : ''}
                    `}
```

- [ ] **Step 3: Dans TerminalWindow.jsx — chrome blanc, pane interne sombre**

Le header (titre, bouton close) doit basculer vers le thème blanc/bleu (mêmes substitutions que Task 8 Step 4).

**Le pane interne console (`<div>` ou `<pre>` qui contient les `terminalEntries`) garde un fond sombre** pour la lisibilité d'un terminal monospace :
- Fond pane : `bg-slate-900` ou `bg-slate-950`
- Texte : `text-slate-100` ou `text-slate-200`
- Ligne courante / prompt : conserver couleur d'accent existante si elle est lisible sur sombre

Audit ciblé :

Run: `grep -n "text-cyan\|border-cyan\|bg-cyan\|bg-gray\|bg-black" "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/src/components/TerminalWindow.jsx"`

Pour chaque match, classer en "header" (→ blanc/bleu) ou "console pane" (→ sombre conservé).

- [ ] **Step 4: Test visuel**

`npm run web` puis ouvrir le Terminal via le menu (s'il est exposé) — sinon vérifier via condition manuelle `showTerminalWindow=true` dans App.jsx en debug, puis remettre.

Note : le terminal s'ouvre via des entrées venant du backend, pas via un bouton direct dans le menu. Si tu ne peux pas l'ouvrir interactivement, le test visuel se fait au moment où le backend déclenche son ouverture. Tu peux tester la mise en page en mettant temporairement le state à `true` puis le remettre.

- [ ] **Step 5: Pas de commit — enchaîner avec Kasa**

---

### Task 10: Refondre KasaWindow

**Files:**
- Modify: `src/components/KasaWindow.jsx`

- [ ] **Step 1: Lire le fichier**

Read `/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/src/components/KasaWindow.jsx` en entier.

- [ ] **Step 2: Auditer et substituer**

Run: `grep -n "text-cyan\|border-cyan\|bg-cyan\|bg-gray-\|bg-black\|text-gray-" "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/src/components/KasaWindow.jsx"`

Substitutions à appliquer (mêmes règles que Task 8) :
- `bg-black/40`, `bg-gray-900/X` → `bg-white/70` ou `bg-white/80`
- `border-cyan-500/X` → `border-blue-400/X`
- `text-cyan-X` → `text-blue-600` (ou `text-slate-700` si rôle texte secondaire)
- `text-gray-400`, `text-gray-300` → `text-slate-500`, `text-slate-700`
- `hover:bg-cyan-900/X` → `hover:bg-blue-50`

Aller fichier par fichier, ligne par ligne.

- [ ] **Step 3: Test visuel**

`npm run web`, cliquer hamburger → ampoule (Kasa). Fenêtre s'ouvre. Tous les éléments lisibles.

- [ ] **Step 4: Pas de commit — enchaîner avec Printer**

---

### Task 11: Refondre PrinterWindow

**Files:**
- Modify: `src/components/PrinterWindow.jsx`

- [ ] **Step 1: Auditer**

Run: `grep -n "text-cyan\|border-cyan\|bg-cyan\|bg-gray-\|bg-black\|text-gray-" "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/src/components/PrinterWindow.jsx"`

- [ ] **Step 2: Substituer selon les mêmes règles que Task 10**

`bg-black/X` → `bg-white/X`, `border-cyan-500/X` → `border-blue-400/X`, `text-cyan-X` → `text-blue-600` ou `text-slate-700`, etc.

- [ ] **Step 3: Test visuel**

`npm run web`, ouvrir Printer via le hamburger.

- [ ] **Step 4: Pas de commit**

---

### Task 12: Refondre SettingsWindow

**Files:**
- Modify: `src/components/SettingsWindow.jsx`

- [ ] **Step 1: Auditer**

Run: `grep -n "text-cyan\|border-cyan\|bg-cyan\|bg-gray-\|bg-black\|text-gray-" "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/src/components/SettingsWindow.jsx"`

- [ ] **Step 2: Substituer selon les mêmes règles**

Cas particuliers possibles :
- Si la fenêtre Settings contient des `<select>` natifs, leur `bg` doit aussi basculer en blanc/clair pour rester cohérent
- Les sliders (cursor sensitivity) — garder leurs colors d'accent comme elles sont si elles fonctionnent sur fond blanc

- [ ] **Step 3: Test visuel**

`npm run web`, ouvrir Settings via le hamburger (icône engrenage).

- [ ] **Step 4: Pas de commit**

---

### Task 13: Refondre DocumentsWindow

**Files:**
- Modify: `src/components/DocumentsWindow.jsx`

- [ ] **Step 1: Auditer**

Run: `grep -n "text-cyan\|border-cyan\|bg-cyan\|bg-gray-\|bg-black\|text-gray-" "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/src/components/DocumentsWindow.jsx"`

- [ ] **Step 2: Substituer**

- [ ] **Step 3: Test visuel**

- [ ] **Step 4: Pas de commit**

---

### Task 14: Refondre ChatModule

**Files:**
- Modify: `src/components/ChatModule.jsx`

- [ ] **Step 1: Auditer**

Run: `grep -n "text-cyan\|border-cyan\|bg-cyan\|bg-gray-\|bg-black\|text-gray-" "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/src/components/ChatModule.jsx"`

- [ ] **Step 2: Substituer**

Le ChatModule contient les bulles de messages et l'input. Garder une distinction visuelle claire entre :
- Message utilisateur : `bg-blue-500 text-white` ou `bg-blue-100 text-blue-900`
- Message Ada : `bg-white/80 text-slate-800 border border-blue-400/30`
- Input : `bg-white/70 border border-blue-400/40 text-slate-800 placeholder:text-slate-400`

- [ ] **Step 3: Test visuel**

`npm run web`, envoyer un message texte dans le chat, vérifier rendu utilisateur + réponse Ada.

- [ ] **Step 4: Commit du Commit 3**

```bash
cd "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis"
git add src/App.jsx src/components/CadWindow.jsx src/components/TerminalWindow.jsx src/components/KasaWindow.jsx src/components/PrinterWindow.jsx src/components/SettingsWindow.jsx src/components/DocumentsWindow.jsx src/components/ChatModule.jsx
git commit -m "feat(windows): translucent white glass theme for modal windows

Les 6 fenêtres modales (CAD, Terminal, Kasa, Printer, Settings, Documents)
+ ChatModule basculent en glass blanc translucide / bordures bleues pour
cohérence avec le fond blanc global. Le pane interne de TerminalWindow
conserve un fond sombre (bg-slate-900) pour la lisibilité monospace.

Aucune logique métier touchée — uniquement classes Tailwind.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Commit 4 — Animations d'ouverture/fermeture des fenêtres

### Task 15: Créer le module windowAnim

**Files:**
- Create: `src/lib/windowAnim.js`

- [ ] **Step 1: Créer le fichier**

Path: `/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/src/lib/windowAnim.js`

Content:

```js
// Variantes Framer Motion partagées par toutes les fenêtres modales
// pour cohérence visuelle de l'ouverture/fermeture.
//
// Origine de la transformation : 'center bottom' — la fenêtre "jaillit"
// depuis la zone du hamburger menu situé au centre-bas.

export const windowVariants = {
    initial: { scale: 0.6, opacity: 0 },
    animate: {
        scale: 1,
        opacity: 1,
        transition: { type: 'spring', stiffness: 280, damping: 24 },
    },
    exit: {
        scale: 0.85,
        opacity: 0,
        transition: { duration: 0.18, ease: 'easeIn' },
    },
};

// Variante allégée pour le mode electron-performance — fade simple.
export const reduceMotionWindowVariants = {
    initial: { opacity: 0 },
    animate: { opacity: 1, transition: { duration: 0.15 } },
    exit: { opacity: 0, transition: { duration: 0.1 } },
};

// Style d'origin partagé.
export const windowMotionStyle = {
    transformOrigin: 'center bottom',
};
```

- [ ] **Step 2: Pas de test visuel — fichier exporté seulement**

---

### Task 16: Wrapper Cad, Terminal, Kasa, Printer, Settings, Documents avec AnimatePresence

**Files:**
- Modify: `src/App.jsx` (imports + chaque fenêtre conditionnelle)

- [ ] **Step 1: Ajouter les imports en haut de App.jsx**

Find:
```jsx
import React, { useEffect, useState, useRef, useMemo } from 'react';
import io from 'socket.io-client';
```

Add after the React import (and before `io`):
```jsx
import { AnimatePresence, motion } from 'framer-motion';
import { windowVariants, reduceMotionWindowVariants, windowMotionStyle } from './lib/windowAnim';
```

- [ ] **Step 2: Définir une constante de variantes effectives juste après `isElectron`**

Find:
```jsx
const isElectron = Boolean(window?.process?.versions?.electron);
```

Add immediately after:
```jsx
const effectiveWindowVariants = isElectron ? reduceMotionWindowVariants : windowVariants;
```

- [ ] **Step 3: Wrapper la CAD Window — pattern wrapper-div pour éviter conflit transform**

**Pourquoi un wrapper-div** : le bloc CAD actuel utilise `transform: translate(-50%, -50%)` pour centrer la fenêtre sur le point `(left, top)`. Framer Motion contrôle aussi `style.transform` pour les anims `scale`. Mettre les deux sur le même élément cause un conflit (FM écrase le centrage). Solution : un `<div>` extérieur gère le centrage CSS, le `<motion.div>` intérieur gère uniquement l'animation.

Find (App.jsx lignes ~2140-2182, le bloc `{showCadWindow && (...)}`):

```jsx
                {/* CAD Window Overlay - Moved outside of Video so it can show independently */}
                {showCadWindow && (
                    <div
                        id="cad"
                        ...
                        onMouseDown={(e) => handleMouseDown(e, 'cad')}
                    >
                        ...
                    </div>
                )}
```

Replace with:

```jsx
                {/* CAD Window Overlay */}
                <AnimatePresence>
                    {showCadWindow && (
                        <div
                            style={{
                                position: 'absolute',
                                left: elementPositions.cad?.x || window.innerWidth / 2,
                                top: elementPositions.cad?.y || window.innerHeight / 2,
                                transform: 'translate(-50%, -50%)',
                                width: `${elementSizes.cad.w}px`,
                                height: `${elementSizes.cad.h}px`,
                                pointerEvents: 'auto',
                                zIndex: getZIndex('cad'),
                            }}
                        >
                            <motion.div
                                id="cad"
                                key="cad"
                                variants={effectiveWindowVariants}
                                initial="initial"
                                animate="animate"
                                exit="exit"
                                onMouseDown={(e) => handleMouseDown(e, 'cad')}
                                style={{
                                    transformOrigin: 'center bottom',
                                    width: '100%',
                                    height: '100%',
                                }}
                                className={`flex flex-col 
                                backdrop-blur-xl bg-white/70 border border-blue-400/40 shadow-2xl overflow-hidden rounded-2xl
                                ${activeDragElement === 'cad' ? 'ring-2 ring-blue-500 bg-blue-500/10' : ''}
                            `}
                            >
                                <div
                                    data-drag-handle
                                    className="h-8 bg-white/60 border-b border-blue-400/30 flex items-center justify-between px-3 cursor-grab active:cursor-grabbing shrink-0"
                                >
                                    <span className="text-xs font-bold tracking-widest text-blue-700">CAD PROTOTYPE</span>
                                    <button
                                        onClick={() => setShowCadWindow(false)}
                                        className="text-slate-500 hover:text-red-500 hover:bg-red-50 p-1 rounded transition-colors"
                                    >
                                        ✕
                                    </button>
                                </div>
                                <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-10 pointer-events-none mix-blend-overlay z-10"></div>
                                <div className="relative z-20 flex-1 min-h-0">
                                    <CadWindow
                                        data={cadData}
                                        thoughts={cadThoughts}
                                        retryInfo={cadRetryInfo}
                                        onClose={() => setShowCadWindow(false)}
                                        socket={socket}
                                    />
                                </div>
                            </motion.div>
                        </div>
                    )}
                </AnimatePresence>
```

**Vérification clé** : la classe `transition-all duration-200` de l'ancien bloc est SUPPRIMÉE — Framer Motion gère désormais les transitions. Garder la transition CSS créerait un double effet.

- [ ] **Step 4: Wrapper la Terminal Window — même pattern wrapper-div**

Find (App.jsx lignes ~2186-2211) :

```jsx
                {/* Terminal Window */}
                {showTerminalWindow && (
                    <div
                        id="terminal"
                        className={`absolute flex flex-col transition-all duration-200
                        backdrop-blur-xl bg-white/70 border border-blue-400/40 shadow-2xl overflow-hidden rounded-lg
                        ${activeDragElement === 'terminal' ? 'ring-2 ring-blue-500 bg-blue-500/10' : ''}
                    `}
                        style={{
                            left: elementPositions.terminal?.x || window.innerWidth / 2 + 100,
                            top: elementPositions.terminal?.y || window.innerHeight / 2 - 100,
                            transform: 'translate(-50%, -50%)',
                            width: '520px',
                            height: '340px',
                            pointerEvents: 'auto',
                            zIndex: getZIndex('terminal')
                        }}
                        onMouseDown={(e) => handleMouseDown(e, 'terminal')}
                    >
                        <div className="relative z-20 w-full h-full">
                            <TerminalWindow
                                entries={terminalEntries}
                                onClose={() => setShowTerminalWindow(false)}
                            />
                        </div>
                    </div>
                )}
```

Replace with:

```jsx
                <AnimatePresence>
                    {showTerminalWindow && (
                        <div
                            style={{
                                position: 'absolute',
                                left: elementPositions.terminal?.x || window.innerWidth / 2 + 100,
                                top: elementPositions.terminal?.y || window.innerHeight / 2 - 100,
                                transform: 'translate(-50%, -50%)',
                                width: '520px',
                                height: '340px',
                                pointerEvents: 'auto',
                                zIndex: getZIndex('terminal'),
                            }}
                        >
                            <motion.div
                                id="terminal"
                                key="terminal"
                                variants={effectiveWindowVariants}
                                initial="initial"
                                animate="animate"
                                exit="exit"
                                onMouseDown={(e) => handleMouseDown(e, 'terminal')}
                                style={{
                                    transformOrigin: 'center bottom',
                                    width: '100%',
                                    height: '100%',
                                }}
                                className={`flex flex-col 
                                backdrop-blur-xl bg-white/70 border border-blue-400/40 shadow-2xl overflow-hidden rounded-lg
                                ${activeDragElement === 'terminal' ? 'ring-2 ring-blue-500 bg-blue-500/10' : ''}
                            `}
                            >
                                <div className="relative z-20 w-full h-full">
                                    <TerminalWindow
                                        entries={terminalEntries}
                                        onClose={() => setShowTerminalWindow(false)}
                                    />
                                </div>
                            </motion.div>
                        </div>
                    )}
                </AnimatePresence>
```

- [ ] **Step 5: Wrapper la Kasa Window**

Find:
```jsx
                {/* Kasa Window */}
                {showKasaWindow && (
                    <KasaWindow ... />
                )}
```

Replace with:
```jsx
                {/* Kasa Window */}
                <AnimatePresence>
                    {showKasaWindow && (
                        <motion.div
                            key="kasa-wrap"
                            variants={effectiveWindowVariants}
                            initial="initial"
                            animate="animate"
                            exit="exit"
                            style={{ transformOrigin: 'center bottom', position: 'absolute', inset: 0, pointerEvents: 'none' }}
                        >
                            <KasaWindow
                                socket={socket}
                                position={elementPositions.kasa}
                                activeDragElement={activeDragElement}
                                setActiveDragElement={setActiveDragElement}
                                devices={kasaDevices}
                                onClose={() => setShowKasaWindow(false)}
                                onMouseDown={(e) => handleMouseDown(e, 'kasa')}
                                zIndex={getZIndex('kasa')}
                            />
                        </motion.div>
                    )}
                </AnimatePresence>
```

Note : `KasaWindow` est un composant qui gère son propre positionnement absolu. On enveloppe dans un `motion.div` qui sert uniquement à l'animation, avec `pointer-events: none` au wrapper pour ne pas bloquer le drag.

- [ ] **Step 6: Wrapper Printer Window — même pattern que Kasa**

```jsx
                <AnimatePresence>
                    {showPrinterWindow && (
                        <motion.div
                            key="printer-wrap"
                            variants={effectiveWindowVariants}
                            initial="initial"
                            animate="animate"
                            exit="exit"
                            style={{ transformOrigin: 'center bottom', position: 'absolute', inset: 0, pointerEvents: 'none' }}
                        >
                            <PrinterWindow
                                socket={socket}
                                onClose={() => setShowPrinterWindow(false)}
                                position={elementPositions.printer}
                                onMouseDown={(e) => handleMouseDown(e, 'printer')}
                                activeDragElement={activeDragElement}
                                setActiveDragElement={setActiveDragElement}
                                zIndex={getZIndex('printer')}
                            />
                        </motion.div>
                    )}
                </AnimatePresence>
```

- [ ] **Step 7: Wrapper SettingsWindow et DocumentsWindow — même pattern**

```jsx
                <AnimatePresence>
                    {showSettings && (
                        <motion.div
                            key="settings-wrap"
                            variants={effectiveWindowVariants}
                            initial="initial"
                            animate="animate"
                            exit="exit"
                            style={{ transformOrigin: 'center bottom', position: 'absolute', inset: 0, pointerEvents: 'none' }}
                        >
                            <SettingsWindow
                                socket={socket}
                                micDevices={micDevices}
                                speakerDevices={speakerDevices}
                                webcamDevices={webcamDevices}
                                selectedMicId={selectedMicId}
                                setSelectedMicId={setSelectedMicId}
                                selectedSpeakerId={selectedSpeakerId}
                                setSelectedSpeakerId={setSelectedSpeakerId}
                                selectedWebcamId={selectedWebcamId}
                                setSelectedWebcamId={setSelectedWebcamId}
                                cursorSensitivity={cursorSensitivity}
                                setCursorSensitivity={setCursorSensitivity}
                                isCameraFlipped={isCameraFlipped}
                                setIsCameraFlipped={setIsCameraFlipped}
                                handleFileUpload={handleFileUpload}
                                onClose={() => setShowSettings(false)}
                            />
                        </motion.div>
                    )}
                </AnimatePresence>

                <AnimatePresence>
                    {showDocumentsWindow && (
                        <motion.div
                            key="documents-wrap"
                            variants={effectiveWindowVariants}
                            initial="initial"
                            animate="animate"
                            exit="exit"
                            style={{ transformOrigin: 'center bottom', position: 'absolute', inset: 0, pointerEvents: 'none' }}
                        >
                            <DocumentsWindow onClose={() => setShowDocumentsWindow(false)} />
                        </motion.div>
                    )}
                </AnimatePresence>
```

- [ ] **Step 8: Test visuel — ouvrir/fermer chaque fenêtre**

`npm run web`. Cliquer hamburger → cliquer chaque icône d'outil et vérifier :
- ✅ Settings : s'ouvre avec scale+fade depuis le bas, se ferme avec exit anim
- ✅ Kasa : idem
- ✅ Printer : idem
- ✅ CAD : idem
- ✅ Documents : idem

Si une fenêtre s'ouvre sans animation → vérifier qu'elle est bien wrapped dans `<AnimatePresence>` ET que la `key` est unique.

Si une fenêtre ne se ferme pas (reste affichée) → vérifier que le state passe bien à `false` (handler de bouton close) ET que `<AnimatePresence>` enveloppe la condition complète.

- [ ] **Step 9: Pas de commit — on traite la caméra**

---

### Task 17: Convertir le camera feed en motion.div toujours monté

**Files:**
- Modify: `src/App.jsx` lignes ~2080-2115 (bloc `<div id="video">`)

- [ ] **Step 1: Remplacer le `<div id="video">` par un `<motion.div>` toujours monté**

Find (App.jsx lignes ~2080-2115) :

```jsx
                <div
                    id="video"
                    className={`fixed bottom-4 right-4 transition-all duration-200 
                        ${isVideoOn ? 'opacity-100' : 'opacity-0 pointer-events-none'} 
                        backdrop-blur-md bg-black/40 border border-white/10 shadow-xl rounded-xl
                    `}
                    style={{ zIndex: 20 }}
                >
                    ...
                </div>
```

Replace with:

```jsx
                <motion.div
                    id="video"
                    animate={isVideoOn ? 'open' : 'closed'}
                    variants={{
                        open: {
                            scale: 1,
                            opacity: 1,
                            transition: { type: 'spring', stiffness: 280, damping: 24 },
                        },
                        closed: {
                            scale: 0.85,
                            opacity: 0,
                            transition: { duration: 0.18, ease: 'easeIn' },
                        },
                    }}
                    className="fixed bottom-4 right-4 backdrop-blur-md bg-white/60 border border-blue-400/40 shadow-xl rounded-xl"
                    style={{
                        zIndex: 20,
                        pointerEvents: isVideoOn ? 'auto' : 'none',
                        transformOrigin: 'center bottom',
                    }}
                >
                    {/* contenu interne (video, canvas, hand debug overlay) INCHANGÉ */}
                    <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-5 pointer-events-none mix-blend-overlay"></div>
                    <div className="relative border border-blue-400/40 rounded-lg overflow-hidden shadow-[0_0_20px_rgba(59,130,246,0.15)] w-80 aspect-video bg-black/80">
                        <video ref={videoRef} autoPlay muted className="absolute inset-0 w-full h-full object-cover opacity-0" />
                        <div className="absolute top-2 left-2 text-[10px] text-blue-700 bg-white/80 backdrop-blur px-2 py-0.5 rounded border border-blue-400/40 z-10 font-bold tracking-wider">CAM_01</div>
                        <canvas
                            ref={canvasRef}
                            className="absolute inset-0 w-full h-full opacity-80"
                            style={{ transform: isCameraFlipped ? 'scaleX(-1)' : 'none' }}
                        />
                        {isHandTrackingEnabled && (
                            <div className="absolute bottom-2 left-2 z-10 text-[10px] leading-4 text-cyan-100 bg-black/70 backdrop-blur px-2 py-1 rounded border border-cyan-500/20">
                                <div>STATE: {handDebug.state}</div>
                                <div>PINCH: {handDebug.pinchRatio === null ? '--' : handDebug.pinchRatio.toFixed(3)}</div>
                                <div>CONF: {handDebug.confidence.toFixed(2)}</div>
                                <div>BOX: {handDebug.interactionInside ? 'IN' : 'EDGE'}</div>
                                <div>RAW: {handDebug.rawCursor ? `${Math.round(handDebug.rawCursor.x)},${Math.round(handDebug.rawCursor.y)}` : '--'}</div>
                                <div>CURSOR: {handDebug.filteredCursor ? `${Math.round(handDebug.filteredCursor.x)},${Math.round(handDebug.filteredCursor.y)}` : '--'}</div>
                                <div>DEAD: {handDebug.deadZone.toFixed(4)}</div>
                            </div>
                        )}
                    </div>
                </motion.div>
```

Note : le hand debug overlay garde son fond noir + cyan car il est superposé à la zone vidéo (fond noir cam) — texte cyan sur noir lisible.

- [ ] **Step 2: Test visuel**

`npm run web`, cliquer hamburger → bouton vidéo. Autoriser la caméra.

Vérifier :
- ✅ La fenêtre vidéo apparaît avec animation scale+fade depuis le bas
- ✅ Le flux webcam s'affiche
- ✅ Re-cliquer le bouton vidéo : la fenêtre disparaît avec exit anim
- ✅ Re-cliquer : la fenêtre réapparaît **sans re-demander l'accès webcam** (preuve que le `<video>` est resté monté)
- ✅ Si on active hand tracking pendant que la cam est OFF, la cam s'ouvre automatiquement (logique de `onToggleHand` dans le menu)

- [ ] **Step 3: Test du chemin critique hand tracking**

Activer le bouton hand tracking depuis le menu. Vérifier que :
- ✅ La cam s'ouvre automatiquement avec l'animation
- ✅ Le squelette de main s'affiche en superposition (canvas)
- ✅ Le cursor virtuel apparaît (curseur via MediaPipe)
- ✅ Pincer pour cliquer fonctionne (test rapide : pincer pour ouvrir/fermer le hamburger)

- [ ] **Step 4: Commit du Commit 4**

```bash
cd "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis"
git add src/lib/windowAnim.js src/App.jsx
git commit -m "feat(windows): scale-fade open animation via Framer Motion

- src/lib/windowAnim.js : variantes Framer Motion partagées
  (windowVariants pour spring scale+fade, reduceMotionWindowVariants
  pour mode electron-performance)
- App.jsx : wrap chaque fenêtre conditionnelle (CAD, Terminal, Kasa,
  Printer, Settings, Documents) dans AnimatePresence + motion.div avec
  transformOrigin 'center bottom'
- Camera feed converti en motion.div toujours monté avec animate open/closed
  pour préserver le stream webcam entre toggles

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Validation finale — Critères d'acceptation §10 du spec

### Task 18: Checklist d'acceptation complète

**Files:** aucun — validation manuelle.

- [ ] **Step 1: Lancer le mode Electron complet**

Run: `cd "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis" && npm run dev`

(lance vite + electron)

- [ ] **Step 2: Cocher chaque critère du spec §10**

Vérifier UN À UN les critères :

- [ ] Fond de l'app est blanc (sauf fenêtres modales qui sont glass blanc translucide)
- [ ] Le visualizer central est une sphère 3D de points bleus qui tourne lentement
- [ ] La sphère pulse visiblement quand Ada parle (intensity > 0.05)
- [ ] Un bouton hamburger à 2 traits est visible au centre-bas, dans un style glass 3D
- [ ] Cliquer le hamburger révèle/masque les 9 boutons d'outils avec une animation staggered
- [ ] Les 9 boutons d'outils ont un look 3D glass (verre frosted + reflet + bordure bleue + glow)
- [ ] Chaque ouverture de fenêtre modale (Cad, Terminal, Kasa, Printer, Settings, Documents) déclenche une animation scale+fade depuis le bas
- [ ] Chaque fermeture déclenche une animation exit (scale 0.85 + fade)
- [ ] Toutes les fonctionnalités existantes (mic, video, hand tracking, drag & drop, etc.) fonctionnent identiquement
- [ ] Aucune erreur console au démarrage
- [ ] Mode `electron-performance` ne casse pas le rendu (fallbacks actifs — vérifié en lançant `npm run dev` qui ouvre Electron, pas web)

- [ ] **Step 3: Si tout coche, push de la branche**

```bash
cd "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis"
git push -u origin feat/ada-redesign-v3
```

- [ ] **Step 4: Mettre à jour le spec avec le statut**

Edit `docs/superpowers/specs/2026-05-18-ada-redesign-design.md` :

Find:
```
**Statut :** Validé — prêt pour planification d'implémentation
```

Replace with:
```
**Statut :** Implémenté — branche `feat/ada-redesign-v3` (commit final à inscrire)
```

Run:
```bash
cd "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis"
git add docs/superpowers/specs/2026-05-18-ada-redesign-design.md
git commit -m "docs(ada): update spec status — redesign v3 implemented

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
git push
```

- [ ] **Step 5: Demander à l'utilisateur s'il veut merge dans main**

Présenter au user : "Plan exécuté. La branche `feat/ada-redesign-v3` est à jour sur origin. Tu veux que je merge dans `main` ou tu préfères tester encore avant ?"

---

## Notes pour l'exécutant

- **N'inverse jamais l'ordre des commits** : chacun dépend du précédent (le hamburger menu n'a de sens qu'après le fond blanc, les anims ont besoin des fenêtres déjà refondues).
- **Ne supprime pas `Visualizer.jsx` et `ToolsModule.jsx`** — ce sont les fallbacks de rollback. Suppression possible dans un commit ultérieur (`chore: remove deprecated Visualizer and ToolsModule`) une fois la v3 stabilisée.
- **En cas d'erreur Three.js dans Electron** (`WebGL context lost`, `Failed to load`) : vérifier que `gl: { alpha: true }` est bien passé à `<Canvas>` et que `dpr` est cappé à 1 en mode `isElectron`.
- **En cas de drag cassé après wrap motion.div** : c'est le cas le plus probable de régression. Le drag est géré par `onMouseDown` qui doit être appliqué soit au `motion.div` parent soit à un `data-drag-handle` enfant. Vérifier que l'événement `mousedown` n'est pas intercepté par le wrapper.
- **Si le linting échoue** : ce projet ne semble pas avoir d'ESLint actif (pas de script `lint` dans `package.json`). Pas de blocage de ce côté.
- **Si l'utilisateur signale "ça ne pulse pas"** : ouvrir devtools, ajouter un log temporaire dans App.jsx pour `audioAmp`. Si la valeur reste à 0, le problème vient du chemin audio mic (analyzer), pas du PointCloudSphere. C'est en dehors du périmètre de ce plan.
