import { b1Scenes } from './scenes-b1'
import { b2Scenes } from './scenes-b2'
import { b3Scenes } from './scenes-b3'
import { b4Scenes } from './scenes-b4'
import type { PreviewScene } from './types'

/**
 * Every scene in the preview harness, in index order.
 *
 * B2-B4 fill in their own scenes-bN.tsx; this file needs no further edits.
 */
export const SCENES: PreviewScene[] = [...b1Scenes, ...b2Scenes, ...b3Scenes, ...b4Scenes]
