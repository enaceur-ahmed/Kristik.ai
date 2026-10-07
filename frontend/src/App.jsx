import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Datasets from './pages/Datasets'
import UploadPage from './pages/UploadPage'
import DatasetDetail from './pages/DatasetDetail'
import ProfilePage from './pages/ProfilePage'
import QualityPage from './pages/QualityPage'
import AIEngineerPage from './pages/AIEngineerPage'
import PipelinePage from './pages/PipelinePage'
import ValidationPage from './pages/ValidationPage'
import AnalyticsPage from './pages/AnalyticsPage'
import ReportPage from './pages/ReportPage'
import BenchmarkPage from './pages/BenchmarkPage'
import DiscussionPage from './pages/DiscussionPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="datasets" element={<Datasets />} />
        <Route path="upload"   element={<UploadPage />} />
        <Route path="datasets/:id" element={<DatasetDetail />}>
          <Route index          element={<ProfilePage />} />
          <Route path="quality"    element={<QualityPage />} />
          <Route path="ai"         element={<AIEngineerPage />} />
          <Route path="pipeline"   element={<PipelinePage />} />
          <Route path="validation" element={<ValidationPage />} />
          <Route path="analytics"  element={<AnalyticsPage />} />
          <Route path="report"     element={<ReportPage />} />
          <Route path="benchmark"  element={<BenchmarkPage />} />
        </Route>
        <Route path="discussion"          element={<DiscussionPage />} />
        <Route path="discussion/:conversationId" element={<DiscussionPage />} />
      </Route>
    </Routes>
  )
}
