import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { HOME_ROUTE } from '../../app/routes'
import { Brand } from '../../components/Brand'
import { Meter } from '../../components/Meter'
import { ConfirmNameStep } from './ConfirmNameStep'
import type { OnboardingStep } from './types'

/**
 * Onboarding runs a sequence of steps and ends on the main app.
 *
 * Only the name step exists today. Resume upload and skill confirmation are the
 * other pair's work, and they slot in by adding an entry to STEPS and a
 * component with the same props — no change to this file's logic. The design
 * shows the step counter and progress bar even for a single step, so the
 * student sees how short this is.
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
    <main className="center-page">
      <div className="onb">
        <Brand className="onb__brand" />
        <div className="onb__step">
          <p className="step-count">
            Step {index + 1} of {STEPS.length}
          </p>
          <Meter
            value={index + 1}
            total={STEPS.length}
            variant="steps"
            label={`Step ${index + 1} of ${STEPS.length}`}
          />
        </div>
        <step.Component key={step.id} onComplete={handleComplete} />
      </div>
    </main>
  )
}
