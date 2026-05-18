# Ada Redesign v3 — Design Specification

**Date :** 2026-05-18
**Auteur :** Bryan (avec assistance Claude Code)
**Projet :** ada-v2 (Electron + React + Vite)
**Statut :** Validé — prêt pour planification d'implémentation
**Contrainte projet impérative :** "il ne faut absolument pas casser le projet"

---

## 1. Objectifs

Refondre l'interface visuelle d'Ada selon une nouvelle identité :

- Fond **blanc global** (substitution du noir actuel)
- **Nuage de points 3D bleus** rotatif comme visualizer central, qui pulse quand Ada parle
- **Menu hamburger** (icône à 2 traits) positionné au centre-bas d'Ada, qui masque/révèle les 9 boutons d'outils
- **Boutons 3D glass** (verre frosted, reflets, élévation hover)
- **Fenêtres modales** (camera, terminal, kasa, printer, settings, documents) repassées en glass blanc translucide / bordures bleues
- **Animation d'ouverture des fenêtres** : scale + fade depuis le bouton source (Framer Motion `AnimatePresence`)

Hors scope :
- Toute modification de logique métier (socket, IPC, hand tracking, audio, brain backend)
- Refonte du composant `MobileApp.jsx` (mode mobile)
- Refonte de l'écran `AuthLock.jsx` (face auth)
- Création de nouveaux outils ou fonctionnalités

---

## 2. Choix verrouillés (sessions de brainstorming)

| # | Question | Réponse retenue |
|---|----------|-----------------|
| 1 | Périmètre du fond blanc | **Toute la fenêtre Ada** |
| 2 | Contenu du hamburger | **Les 9 boutons d'outils uniquement** (top bar reste visible) |
| 3 | Forme du nuage de points | **Sphère 3D rotative** (Three.js, ~2000 points) |
| 4 | Style des fenêtres modales | **Glass blanc translucide / bordures bleues** |
| 5 | Animation d'ouverture | **Scale 0.6 → 1 + opacity 0 → 1, spring 280ms, origine = bouton source** |

---

## 3. Architecture des composants

### 3.1 Nouveaux fichiers

| Fichier | Rôle | Dépendances |
|---------|------|-------------|
| `src/components/PointCloudSphere.jsx` | Visualizer central : sphère 3D de ~2000 points bleus. Props : `isSpeaking: boolean`, `intensity: number` (0–1), `reduceMotion: boolean`, `width`, `height` | `@react-three/fiber`, `three` (déjà installés) |
| `src/components/GlassButton.jsx` | Bouton 3D glass paramétrable. Props : `icon: ReactNode`, `label?: string`, `isActive?: boolean`, `accentColor?: string`, `disabled?: boolean`, `onClick`, `title?` | `framer-motion` (hover anim) |
| `src/components/HamburgerMenu.jsx` | Orchestre l'état ouvert/fermé, affiche le bouton `≡` au centre-bas et déroule les 9 `<GlassButton>` au-dessus avec stagger. Props : reprend la même API que `ToolsModule.jsx` actuel | `framer-motion` |
| `src/lib/windowAnim.js` | Exporte `windowVariants` (object Framer Motion) partagé par toutes les fenêtres modales pour cohérence d'animation | aucune |

### 3.2 Fichiers modifiés (impact contrôlé)

| Fichier | Nature du changement |
|---------|----------------------|
| `src/index.css` | `body { background: #fff }` ; ajout de tokens CSS (`--ada-blue-accent`, `--ada-blue-glow`, `--ada-glass-bg`, `--ada-glass-border`) ; ajout `.electron-performance` overrides pour les nouveaux composants |
| `src/App.jsx` | (1) Remplace `<Visualizer>` par `<PointCloudSphere>` à l'emplacement du visualizer central. (2) Remplace `<ToolsModule>` par `<HamburgerMenu>`. (3) Wrap chaque fenêtre conditionnelle (Cad, Terminal, Kasa, Printer, Settings, Documents, Browser) dans `<AnimatePresence>` + `<motion.div>` avec `windowVariants`. (4) Bascule des classes `text-cyan-*` / `border-cyan-*` / `bg-cyan-*` qui se retrouvent sur fond blanc en équivalents bleus/sombres lisibles. **Aucune logique touchée** (handlers, refs, sockets, state). |
| `src/components/CadWindow.jsx` | Fond glass noir → glass blanc translucide ; bordure cyan → bleue ; textes blancs/cyan → sombres pour lisibilité sur glass blanc. **Logique inchangée.** |
| `src/components/TerminalWindow.jsx` | **Chrome de la fenêtre** (header, bordure, ombre) → glass blanc + bordure bleue. **Pane interne console** → conserve fond sombre `bg-slate-900` + texte clair monospace (lisibilité prioritaire pour un terminal). |
| `src/components/KasaWindow.jsx` | Idem. |
| `src/components/PrinterWindow.jsx` | Idem. |
| `src/components/SettingsWindow.jsx` | Idem. |
| `src/components/DocumentsWindow.jsx` | Idem. |
| `src/components/ChatModule.jsx` | Bascule du fond/bordures vers le thème glass blanc. **Logique de messages inchangée.** |

**Hors scope confirmé** : `src/components/BrowserWindow.jsx` est importé dans `App.jsx` mais jamais rendu (orphelin). Le composant n'est PAS retouché dans cette v3. Si réactivé plus tard, il devra être refait dans une itération séparée.

### 3.3 Fichiers conservés en l'état (fallback)

- `src/components/Visualizer.jsx` — non supprimé. Permet un rollback rapide en réimportant ce composant à la place de `PointCloudSphere`. À supprimer dans un commit ultérieur après stabilisation.
- `src/components/ToolsModule.jsx` — non supprimé. Référence stylistique pour `GlassButton.jsx`. À supprimer après stabilisation.
- Tout le backend (`backend/`, `brain/`) — intouché.
- `electron/main.js`, `vite.config.js`, `package.json` — intouchés (toutes les dépendances nécessaires sont déjà installées).

---

## 4. Spécification détaillée — PointCloudSphere

### 4.1 Structure JSX

```jsx
<Canvas dpr={reduceMotion ? 1 : [1, 2]} camera={{ position: [0, 0, 3], fov: 50 }}>
  <ambientLight intensity={0.5} />
  <PointsCluster
    count={2000}
    radius={1.0}
    isSpeaking={isSpeaking}
    intensity={intensity}
    reduceMotion={reduceMotion}
  />
</Canvas>
```

### 4.2 Génération des positions (sphère Fibonacci)

```
Pour i de 0 à count-1 :
  φ = acos(1 - 2 * (i + 0.5) / count)
  θ = π * (1 + √5) * (i + 0.5)
  position[i] = [radius * sin(φ) * cos(θ),
                 radius * cos(φ),
                 radius * sin(φ) * sin(θ)]
```

Sauvegarder ces positions initiales dans un `Float32Array` de référence (`originalPositions`) pour calculer les déplacements radiaux relatifs.

### 4.3 Matériel

- `PointsMaterial`
- `color` : `#3b82f6` (Tailwind blue-500) au repos ; lerp vers `#2563eb` (blue-600) si `intensity > 0.6`
- `size` : `0.04` (`0.06` quand isSpeaking, lerp pour transition douce)
- `sizeAttenuation` : `true`
- `transparent` : `true`
- `opacity` : `0.85`
- `depthWrite` : `false` (évite les artefacts de tri sur les points superposés)

### 4.4 Animation (`useFrame`)

À chaque frame :

1. **Rotation** : `points.rotation.y += isSpeaking ? 0.003 : 0.0008` (multiplié par 0.3 si `reduceMotion`)
2. **Déplacement radial des points** :
   - Si `isSpeaking` : pour chaque point, `position = originalPosition × (1 + intensity × 0.15 × (1 + sin(t × 8 + i × 0.1) × 0.3))`
   - Sinon (idle) : breathing global `position = originalPosition × (1 + sin(t * 1.5) × 0.02)`
   - Flag `geometry.attributes.position.needsUpdate = true`
3. **Couleur du matériel** : lerp `color` selon `intensity` (utilise `Color.lerpColors`)

Si `reduceMotion === true`, désactiver le déplacement radial individuel — garder seulement le breathing global, et baisser la rotation.

### 4.5 Performance

- Une seule instance `BufferGeometry` réutilisée (pas de re-création par frame)
- Mutation directe de `position.array` (pas d'allocation)
- Un seul draw call (PointsMaterial natif Three.js)
- `dpr` clamped à `[1, 2]` (évite la sur-résolution sur Retina)
- En mode `electron-performance`, `dpr` forcé à 1 et nombre de points réduit à 1000

---

## 5. Spécification détaillée — GlassButton

### 5.1 Style "verre 3D" (Tailwind + style inline)

Empilement de couches :

| Couche | Implémentation |
|--------|----------------|
| Backdrop | `backdrop-blur-xl` + `backdrop-saturate-150` |
| Background | `bg-gradient-to-br from-white/70 to-white/40` |
| Bordure | `border border-blue-400/40` |
| Inset highlight | `shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]` |
| Outer glow | `shadow-[0_8px_32px_rgba(59,130,246,0.15)]` |
| Reflet diagonal | Pseudo-élément `::before` en `linear-gradient(135deg, rgba(255,255,255,0.5) 0%, transparent 50%)` (via une `<span>` absolument positionnée puisque Tailwind ne génère pas de `::before` avec gradient complexe directement) |
| Forme | `rounded-full` (idem look actuel), `p-3` |

### 5.2 États

| État | Modifications |
|------|---------------|
| Au repos | Comme ci-dessus |
| Hover | `translateY(-2px)`, glow renforcé `shadow-[0_12px_40px_rgba(59,130,246,0.25)]`, reflet décalé légèrement via transition CSS |
| Active (`isActive=true`) | `bg-blue-500/90`, icône blanche, glow intensifié, bordure `border-blue-300/80` |
| Disabled | `opacity-40`, `pointer-events-none` |
| Mode `electron-performance` | Le `backdrop-blur` est supprimé (cf. `index.css` actuel) ; on fallback sur `bg-white/85` opaque ; le reflet ::before est aussi désactivé pour économiser un compositing layer |

### 5.3 API du composant

```tsx
interface GlassButtonProps {
  icon: ReactNode;           // lucide-react icon (size géré en interne)
  isActive?: boolean;        // toggle state
  accentColor?: string;      // override Tailwind class for accent (default: 'blue')
  disabled?: boolean;
  onClick: () => void;
  title?: string;            // tooltip natif
  ariaLabel?: string;
}
```

L'`accentColor` permet de garder les couleurs spécifiques actuelles (vert pour Power, rouge pour mic muted, violet pour video, orange pour hand, jaune pour Kasa, etc.) — chaque appel dans `HamburgerMenu` passe sa couleur.

---

## 6. Spécification détaillée — HamburgerMenu

### 6.1 Structure

```jsx
<div className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-3 pointer-events-auto">
  <AnimatePresence>
    {isOpen && (
      <motion.div
        key="tools-row"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0, transition: { staggerChildren: 0.03 } }}
        exit={{ opacity: 0, y: 10, transition: { duration: 0.15 } }}
        className="flex gap-3"
      >
        {/* 9 GlassButtons mappés depuis un array de configs */}
      </motion.div>
    )}
  </AnimatePresence>
  <HamburgerToggleButton isOpen={isOpen} onClick={() => setIsOpen(!isOpen)} />
</div>
```

### 6.2 Bouton hamburger (`HamburgerToggleButton`)

Un `GlassButton` spécialisé qui affiche deux traits horizontaux en SVG :

- État fermé : deux lignes parallèles centrées (≡ à 2 traits)
- État ouvert : les deux lignes se croisent (× — rotation +45°/-45° de chaque ligne)
- Transition Framer Motion : 200ms ease-in-out
- Taille légèrement plus grande que les autres boutons (`p-4` au lieu de `p-3`)

### 6.3 Position et z-index

- Position : `absolute bottom-10 left-1/2 -translate-x-1/2` (centre-bas de la fenêtre principale, donc sous le visualizer central)
- z-index : 30 (au-dessus du visualizer mais sous les fenêtres modales qui sont à 40+)
- En mode `isModularMode` (mode "drag & drop") : conserver le comportement actuel (les outils restent draggable via `position` prop) — la logique de `position` de `App.jsx` ligne 128 est passée au menu.

### 6.4 API du composant

Reprend **exactement** l'API actuelle de `ToolsModule.jsx` (mêmes props, mêmes handlers) pour minimiser l'impact sur `App.jsx`. Le seul changement côté App est l'import.

---

## 7. Spécification détaillée — Animations des fenêtres modales

### 7.1 Variantes partagées (`src/lib/windowAnim.js`)

```js
export const windowVariants = {
  initial: { scale: 0.6, opacity: 0 },
  animate: {
    scale: 1,
    opacity: 1,
    transition: { type: 'spring', stiffness: 280, damping: 24 }
  },
  exit: {
    scale: 0.85,
    opacity: 0,
    transition: { duration: 0.18, ease: 'easeIn' }
  },
};

export const reduceMotionWindowVariants = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: 0.15 } },
  exit: { opacity: 0, transition: { duration: 0.1 } },
};
```

### 7.2 Application dans `App.jsx`

Pour chaque fenêtre conditionnellement rendue :

```jsx
<AnimatePresence>
  {showCadWindow && (
    <motion.div
      key="cad"
      variants={isElectronPerformance ? reduceMotionWindowVariants : windowVariants}
      initial="initial" animate="animate" exit="exit"
      style={{
        transformOrigin: 'center bottom',
        // ... reste du positioning style existant
      }}
      // ... reste des props existantes (id, className, onMouseDown, etc.)
    >
      <CadWindow ... />
    </motion.div>
  )}
</AnimatePresence>
```

### 7.3 Fenêtres concernées (rendering conditionnel + `AnimatePresence`)

| Fenêtre | Variable conditionnelle | `key` |
|---------|------------------------|-------|
| CAD | `showCadWindow` | `'cad'` |
| Terminal | `showTerminalWindow` | `'terminal'` |
| Kasa | `showKasaWindow` | `'kasa'` |
| Printer | `showPrinterWindow` | `'printer'` |
| Settings | `showSettings` | `'settings'` |
| Documents | `showDocumentsWindow` | `'documents'` |

### 7.4 Cas particulier — camera feed

Le conteneur `<video>` (lignes 2080-2115 de App.jsx) est **toujours monté** (le démonter relancerait la requête webcam à chaque ouverture). Il utilise un toggle d'opacity. On garde le composant monté mais on remplace le toggle d'opacity par un `motion.div` qui anime selon `isVideoOn` :

```jsx
<motion.div
  id="video"
  animate={isVideoOn ? 'open' : 'closed'}
  variants={{
    open: { scale: 1, opacity: 1, transition: { type: 'spring', stiffness: 280, damping: 24 } },
    closed: { scale: 0.85, opacity: 0, transition: { duration: 0.18 } },
  }}
  style={{ pointerEvents: isVideoOn ? 'auto' : 'none', transformOrigin: 'center bottom', /* … */ }}
>
  {/* video, canvas, hand debug overlay inchangés */}
</motion.div>
```

Le `<video>` HTML reste tel quel à l'intérieur — pas de remount, pas de fuite de stream webcam. Le `pointerEvents` géré dynamiquement remplace l'actuel `opacity-0 pointer-events-none`.

---

## 8. Migration des couleurs cyan → bleu/sombre

### 8.1 Audit nécessaire

Avant chaque commit, exécuter dans `src/` :

```bash
grep -rn "text-cyan-\|border-cyan-\|bg-cyan-\|from-cyan-\|to-cyan-\|via-cyan-\|shadow-\[.*cyan\|drop-shadow-\[.*cyan" src/
```

Pour chaque résultat, classer en deux catégories :

1. **Sur fond blanc** (top bar, project label, status indicators visibles dans la zone Ada) → bascule vers `text-blue-700` / `border-blue-400` / `bg-blue-50` selon le rôle. Texte body sombre = `text-slate-700`. Texte secondaire = `text-slate-500`.
2. **Dans une fenêtre modale glass blanc** → bascule vers `text-blue-600` ou `text-slate-700` selon contraste.

### 8.2 Tokens CSS à ajouter dans `index.css`

```css
:root {
  --ada-blue-accent: #3b82f6;    /* blue-500 */
  --ada-blue-strong: #2563eb;    /* blue-600 */
  --ada-blue-soft: #dbeafe;      /* blue-100 */
  --ada-glass-bg: rgba(255,255,255,0.6);
  --ada-glass-border: rgba(59,130,246,0.4);
  --ada-glass-glow: rgba(59,130,246,0.15);
}
```

---

## 9. Stratégie anti-régression

### 9.1 Préservation des chemins critiques

Les éléments suivants doivent rester **fonctionnellement identiques** après le redesign :

- Connexion socket.io au backend (port 8000)
- IPC Electron (minimize, maximize, close, etc.)
- Toggle Power (`isConnected`) — gate qui désactive mic/video
- Toggle Mic (`isMuted`)
- Toggle Video et démarrage du flux webcam
- Hand tracking (MediaPipe) avec son cursor, ripples, gestures
- Mode `isModularMode` (drag & drop des éléments) — drag handles préservés
- Mode `isScreenMode` (Ada voit l'écran)
- Tous les confirmation popups (`ConfirmationPopup`)
- Memory prompt si réactivé
- Auth lock (face auth)
- Mobile app (route distincte, hors scope)

### 9.2 Mode performance Electron

`index.css` actuel désactive déjà blurs et animations lourdes en mode `electron-performance`. Cette classe est appliquée sur le root quand `isElectron === true`. Les nouveaux composants doivent respecter ce flag :

- `PointCloudSphere` : DPR à 1, count à 1000, animations simplifiées
- `GlassButton` : pas de backdrop-blur (fallback opaque), pas de reflet ::before
- `windowVariants` : utiliser `reduceMotionWindowVariants` (fade simple)

### 9.3 Tests manuels obligatoires avant merge

1. `npm run dev` démarre sans erreur console (ni vite, ni electron, ni backend si lancé en parallèle)
2. Le visualizer affiche la sphère ; elle pulse quand on parle au mic
3. Le hamburger ouvre et ferme correctement
4. Cliquer chaque bouton dans le menu :
   - Power : toggle vert ↔ gris ; gate mic/video correctement
   - Mic : toggle cyan ↔ rouge muted
   - Video : ouvre/ferme le feed caméra
   - Settings : ouvre la fenêtre Settings avec animation scale+fade
   - Hand : active hand tracking (vérifier que MediaPipe charge)
   - Kasa : ouvre la fenêtre Kasa avec animation
   - Printer : idem
   - CAD : idem
   - Screen Mode : toggle vert
   - Documents : ouvre la fenêtre Documents avec animation
5. Drag & drop des éléments (modular mode) fonctionne toujours
6. Fermeture de chaque fenêtre déclenche l'exit animation puis unmount
7. Quitter et relancer : l'état persiste (localStorage)

### 9.4 Séquencement des commits

| # | Sujet | Périmètre |
|---|-------|-----------|
| 1 | `feat(visualizer): 3D point cloud sphere replaces canvas circle` | `PointCloudSphere.jsx` + remplacement dans `App.jsx` (rien d'autre) |
| 2 | `feat(ui): white background + hamburger menu + 3D glass buttons` | `index.css` (fond blanc + tokens), `GlassButton.jsx`, `HamburgerMenu.jsx`, remplacement dans `App.jsx`, audit cyan → bleu/sombre dans `App.jsx` |
| 3 | `feat(windows): translucent white glass theme` | Refactoring stylistique des 6+ fenêtres (Cad, Terminal, Kasa, Printer, Settings, Documents, +Browser, +Chat) |
| 4 | `feat(windows): scale-fade open animation via Framer Motion` | `lib/windowAnim.js` + wrapping dans `App.jsx` |

Chaque commit est testable indépendamment et un rollback granulaire reste possible.

### 9.5 Stratégie de branche

Travailler sur une branche dédiée `feat/ada-redesign-v3` (à créer depuis l'état git actuel). Ne pas merger dans `main` tant que les 4 commits ne sont pas tous validés par tests manuels.

---

## 10. Critères d'acceptation

Le redesign est considéré comme terminé quand TOUS les critères suivants sont vrais :

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
- [ ] Tests manuels de §9.3 tous OK
- [ ] Mode `electron-performance` ne casse pas le rendu (fallbacks actifs)

---

## 11. Risques identifiés

| Risque | Probabilité | Mitigation |
|--------|-------------|------------|
| Sphère 3D consomme trop de GPU sur Electron | Moyenne | DPR cappé, count réduit en mode perf, fallback opacité simple |
| Backdrop-blur sur les boutons fait laguer la fenêtre Electron | Moyenne | Déjà désactivé en mode `electron-performance` (CSS existant) — on continue ce pattern |
| L'audit cyan → bleu/sombre oublie un élément qui devient illisible (cyan clair sur blanc) | Moyenne | Grep systématique avant chaque commit + tests visuels manuels |
| Wrapping `motion.div` autour d'une fenêtre casse son `onMouseDown` ou son drag handle | Faible | Le `motion.div` est un simple wrapper ; les enfants conservent leurs handlers. À tester explicitement pour le mode modular. |
| Three.js échoue à charger dans Electron (issues anciennes connues sur certaines versions) | Faible | `@react-three/fiber` 8.15 + `three` 0.160 déjà testés ensemble — déjà dans `package.json` donc validé |
| Refonte de chaque fenêtre introduit une régression de contraste (texte illisible sur glass blanc) | Moyenne | Tests visuels manuels obligatoires par fenêtre dans §9.3 |

---

## 12. Étape suivante

Après validation de ce spec par l'utilisateur :

1. Création du plan d'implémentation détaillé via la skill `superpowers:writing-plans`
2. Le plan découpera l'implémentation en tâches atomiques alignées avec les 4 commits de §9.4
3. L'exécution se fera en branche `feat/ada-redesign-v3`
