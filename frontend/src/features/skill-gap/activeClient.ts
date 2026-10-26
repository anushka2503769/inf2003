import { env } from '../../lib/env'
import { createDefaultSkillGapClient } from './client'
import { createRealSkillGapClient } from './realClient'

// The real API by default; VITE_DATA=mock switches to synthetic data.
export const skillGapClient = env.useMockData ? createDefaultSkillGapClient() : createRealSkillGapClient()
