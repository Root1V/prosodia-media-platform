import type { ReactNode } from 'react'
import { Navigate, Route, BrowserRouter, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from './context/AuthContext'
import { ThemeProvider } from './context/ThemeContext'
import { ProtectedRoute } from './components/ProtectedRoute'
import { AppShell } from './components/layout/AppShell'
import { LoginPage } from './pages/LoginPage'
import { DashboardHomePage } from './pages/DashboardHomePage'
import { ProjectsListPage } from './pages/ProjectsListPage'
import { ProjectDetailPage } from './pages/ProjectDetailPage'
import { NewDubbingProjectPage } from './pages/NewDubbingProjectPage'
import { NewSubtitlesProjectPage } from './pages/NewSubtitlesProjectPage'
import { NewTranscriptionProjectPage } from './pages/NewTranscriptionProjectPage'
import { NewTtsProjectPage } from './pages/NewTtsProjectPage'
import { NewMicroVideoProjectPage } from './pages/NewMicroVideoProjectPage'
import { MicroVideoObjectivePage } from './pages/MicroVideoObjectivePage'
import { UsersListPage } from './pages/UsersListPage'
import { MusicTracksPage } from './pages/MusicTracksPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

function ProtectedPage({
  children,
  adminOnly,
  fullBleed,
}: {
  children: ReactNode
  adminOnly?: boolean
  fullBleed?: boolean
}) {
  return (
    <ProtectedRoute adminOnly={adminOnly}>
      <AppShell fullBleed={fullBleed}>{children}</AppShell>
    </ProtectedRoute>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route
                path="/"
                element={
                  <ProtectedPage>
                    <DashboardHomePage />
                  </ProtectedPage>
                }
              />
              <Route
                path="/dubbing/new"
                element={
                  <ProtectedPage>
                    <NewDubbingProjectPage />
                  </ProtectedPage>
                }
              />
              <Route
                path="/subtitles/new"
                element={
                  <ProtectedPage>
                    <NewSubtitlesProjectPage />
                  </ProtectedPage>
                }
              />
              <Route
                path="/transcription/new"
                element={
                  <ProtectedPage>
                    <NewTranscriptionProjectPage />
                  </ProtectedPage>
                }
              />
              <Route
                path="/tts/new"
                element={
                  <ProtectedPage>
                    <NewTtsProjectPage />
                  </ProtectedPage>
                }
              />
              {/* La eleccion de objetivo (RM-42) va ANTES del editor y sin
                  fullBleed: es una pagina normal con el padding del shell, no
                  un lienzo a sangre como el editor. */}
              <Route
                path="/micro-video"
                element={
                  <ProtectedPage>
                    <MicroVideoObjectivePage />
                  </ProtectedPage>
                }
              />
              <Route
                path="/micro-video/new"
                element={
                  <ProtectedPage fullBleed>
                    <NewMicroVideoProjectPage />
                  </ProtectedPage>
                }
              />
              <Route
                path="/projects"
                element={
                  <ProtectedPage>
                    <ProjectsListPage />
                  </ProtectedPage>
                }
              />
              <Route
                path="/projects/:id"
                element={
                  <ProtectedPage>
                    <ProjectDetailPage />
                  </ProtectedPage>
                }
              />
              <Route
                path="/users"
                element={
                  <ProtectedPage adminOnly>
                    <UsersListPage />
                  </ProtectedPage>
                }
              />
              <Route
                path="/music-tracks"
                element={
                  <ProtectedPage adminOnly>
                    <MusicTracksPage />
                  </ProtectedPage>
                }
              />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  )
}
