import { fetchMusicSampleUrl } from '../../../api/samples'
import { SamplePreviewButton } from '../../media/SamplePreviewButton'
import { SelectableCard } from '../../ui/SelectableCard'
import { MUSIC_CATEGORY_LABELS } from '../../../lib/labels'
import type { MusicCategory, MusicTrack } from '../../../types/musicTracks'

const MUSIC_CATEGORIES = Object.keys(MUSIC_CATEGORY_LABELS) as MusicCategory[]

interface MusicPanelProps {
  musicTracks: MusicTrack[]
  backgroundMusic: string | null
  onSelectMusic: (id: string | null) => void
  /** Categoria que el objetivo del video ofrece primero (ver RM-42 y
   * lib/objectives.ts). null = el orden de siempre. No preselecciona nada:
   * mueve la categoria al principio de la lista, nada mas -- las demas siguen
   * ahi y "Sin musica" sigue siendo el estado inicial. */
  suggestedCategory?: MusicCategory | null
}

export function MusicPanel({
  musicTracks,
  backgroundMusic,
  onSelectMusic,
  suggestedCategory,
}: MusicPanelProps) {
  const categories = suggestedCategory
    ? [suggestedCategory, ...MUSIC_CATEGORIES.filter((c) => c !== suggestedCategory)]
    : MUSIC_CATEGORIES

  return (
    <div className="flex flex-col gap-1.5">
      <SelectableCard selected={backgroundMusic === null} onSelect={() => onSelectMusic(null)}>
        <span className="text-sm font-medium">Sin música</span>
        <span className="text-xs text-muted-foreground">Solo la narración</span>
      </SelectableCard>
      {categories.map((cat) => {
        const categoryTracks = musicTracks.filter((t) => t.category === cat)
        if (categoryTracks.length === 0) return null
        return (
          <div key={cat} className="mt-2 flex flex-col gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">{MUSIC_CATEGORY_LABELS[cat]}</span>
            <div className="flex flex-col gap-2">
              {categoryTracks.map((track) => (
                <SelectableCard
                  key={track.id}
                  selected={backgroundMusic === track.id}
                  onSelect={() => onSelectMusic(track.id)}
                >
                  <div className="flex w-full items-center justify-between gap-2">
                    <span className="text-sm font-medium">{track.title}</span>
                    <SamplePreviewButton
                      sampleKey={`music-${track.id}`}
                      fetchUrl={() => fetchMusicSampleUrl(track.id)}
                    />
                  </div>
                </SelectableCard>
              ))}
            </div>
          </div>
        )
      })}
      <p className="mt-2 text-xs text-muted-foreground">
        Se mezcla en volumen bajo, sin tapar la narración. El fragmento a usar se recorta abajo, en la
        pista de audio.
      </p>
    </div>
  )
}
