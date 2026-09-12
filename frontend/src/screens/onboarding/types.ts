import type { ComponentType } from 'react'

/**
 * Every onboarding step receives the same props: it does its own work and calls
 * `onComplete` when the student can move on. A step is responsible for its own
 * saving and its own errors, so a failure never advances the sequence.
 */
export interface OnboardingStepProps {
  onComplete: () => void
}

export interface OnboardingStep {
  id: string
  Component: ComponentType<OnboardingStepProps>
}
