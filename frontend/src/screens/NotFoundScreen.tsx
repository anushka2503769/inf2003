import { useLocation, useNavigate } from 'react-router-dom'

import { FullPageMessage } from '../components/Feedback'
import { HOME_ROUTE } from '../app/routes'

export function NotFoundScreen() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  return (
    <FullPageMessage
      eyebrow="404"
      icon="compass"
      title="This page is also jobless."
      body={
        <>
          Nothing lives at <code>{pathname}</code>. It may have moved, or it never existed.
        </>
      }
      actionLabel="Go to Discover"
      actionIconRight="arrow-right"
      onAction={() => navigate(HOME_ROUTE, { replace: true })}
    />
  )
}
