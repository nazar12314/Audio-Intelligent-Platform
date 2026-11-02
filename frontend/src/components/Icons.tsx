import type { ReactNode, SVGProps } from 'react'

function Icon({ children, ...props }: SVGProps<SVGSVGElement> & { children: ReactNode }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  )
}

type P = SVGProps<SVGSVGElement>

export const WaveIcon = (p: P) => (
  <Icon {...p}>
    <path d="M3 10v4M7 7v10M11 4v16M15 8v8M19 10v4" />
  </Icon>
)
export const PlusIcon = (p: P) => (
  <Icon {...p}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
)
export const SearchIcon = (p: P) => (
  <Icon {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.5-3.5" />
  </Icon>
)
export const UploadIcon = (p: P) => (
  <Icon {...p}>
    <path d="M7 18a4 4 0 0 1-.6-7.95A6 6 0 0 1 18 9a4.5 4.5 0 0 1 0 9" />
    <path d="M12 12v8M9 15l3-3 3 3" />
  </Icon>
)
export const CopyIcon = (p: P) => (
  <Icon {...p}>
    <rect x="9" y="9" width="11" height="11" rx="2" />
    <path d="M5 15V5a2 2 0 0 1 2-2h8" />
  </Icon>
)
export const PlayIcon = (p: P) => (
  <Icon {...p} fill="currentColor" stroke="none">
    <path d="M8 5.5v13l11-6.5z" />
  </Icon>
)
export const PauseIcon = (p: P) => (
  <Icon {...p} fill="currentColor" stroke="none">
    <rect x="7" y="5" width="4" height="14" rx="1" />
    <rect x="13" y="5" width="4" height="14" rx="1" />
  </Icon>
)
export const VolumeIcon = (p: P) => (
  <Icon {...p}>
    <path d="M11 5 6 9H3v6h3l5 4z" />
    <path d="M15.5 8.5a5 5 0 0 1 0 7" />
  </Icon>
)
export const FileAudioIcon = (p: P) => (
  <Icon {...p}>
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
    <path d="M14 3v5h5M9 13v3M12 11v7M15 13v3" />
  </Icon>
)
export const ClockIcon = (p: P) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </Icon>
)
export const DriveIcon = (p: P) => (
  <Icon {...p}>
    <rect x="3" y="6" width="18" height="12" rx="2" />
    <path d="M7 14h.01M3 12h18" />
  </Icon>
)
export const SpeechIcon = (p: P) => (
  <Icon {...p}>
    <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />
  </Icon>
)
export const CheckIcon = (p: P) => (
  <Icon {...p}>
    <path d="m5 12 5 5L20 7" />
  </Icon>
)
export const XIcon = (p: P) => (
  <Icon {...p}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Icon>
)
