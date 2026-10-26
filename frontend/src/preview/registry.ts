import { b1Scenes } from './scenes-b1'
import type { PreviewScene } from './types'

/**
 * Every scene in the preview harness, in index order.
 *
 * B2-B4: add a `scenes-b2.tsx` (etc.) exporting a PreviewScene[] and spread it
 * here. One import and one spread per PR keeps merges trivial.
 */
export const SCENES: PreviewScene[] = [...b1Scenes]
