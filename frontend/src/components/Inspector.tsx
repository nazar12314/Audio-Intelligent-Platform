import type { Processing, Recording } from '../api'
import { pipelineSteps } from '../derive'
import { CheckIcon, XIcon } from './Icons'

export function Inspector({
  recording,
  processing,
  notProcessed,
}: {
  recording: Recording | null
  processing: Processing | null
  notProcessed: boolean
}) {
  return (
    <aside className="inspector">
      <div className="eyebrow inspector__title">Processing</div>
      {recording ? (
        <ol className="steps">
          {pipelineSteps(recording, processing, notProcessed).map((step) => (
            <li key={step.title} className={`step step--${step.state}`}>
              <span className="step__marker">
                {step.state === 'done' && <CheckIcon width={12} height={12} />}
                {step.state === 'failed' && <XIcon width={12} height={12} />}
              </span>
              <div>
                <strong>{step.title}</strong>
                <div className="muted small">{step.detail}</div>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted small">Select a recording.</p>
      )}
    </aside>
  )
}
