import { createDefaultSkillGapClient } from './client'

// Real-client switch: replace the import above with
// `import { createRealSkillGapClient as createDefaultSkillGapClient } from './realClient'`.
export const skillGapClient = createDefaultSkillGapClient()
