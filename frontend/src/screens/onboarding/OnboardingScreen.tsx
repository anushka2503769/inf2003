import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { HOME_ROUTE } from '../../app/routes'
import { ConfirmNameStep } from './ConfirmNameStep'
import type { OnboardingStep } from './types'

/**
 * Onboarding runs a sequence of steps and ends on the main app.
 *
 * Only the name step exists today. Resume upload and skill confirmation are the
 * other pair's work, and they slot in by adding an entry to STEPS and a
 * component with the same props — no change to this file's logic. The step
 * counter appears only once there is more than one step, because "Step 1 of 1"
 * is noise.
 */
const STEPS: OnboardingStep[] = [
  { id: 'name', Component: ConfirmNameStep },
  // { id: 'resume', Component: UploadResumeStep },
  // { id: 'skills', Component: ConfirmSkillsStep },
]

export function OnboardingScreen() {
  const navigate = useNavigate()
  const [index, setIndex] = useState(0)

  const step = STEPS[index]
  const isLast = index === STEPS.length - 1

  function handleComplete() {
    if (isLast) {
      navigate(HOME_ROUTE, { replace: true })
      return
    }
    setIndex(current => current + 1)
  }

  return (
    <div className="entry">
      <div className="entry__panel">
        {STEPS.length > 1 ? (
          <p className="step-count">
            Step {index + 1} of {STEPS.length}
          </p>
        ) : null}
        <step.Component key={step.id} onComplete={handleComplete} />
      </div>
    </div>
  )
}
