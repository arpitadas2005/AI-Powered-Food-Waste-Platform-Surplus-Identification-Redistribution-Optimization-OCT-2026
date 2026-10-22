import React, { useState, useEffect } from 'react';
import { ActiveTab, Navigation } from './components/Navigation';
import { DashboardView } from './components/DashboardView';
import { InventoryListView } from './components/InventoryListView';
import { BarcodeScanner } from './components/BarcodeScanner';
import { ExpiryAlertsView } from './components/ExpiryAlertsView';
import { CsvImportView } from './components/CsvImportView';
import { PosIntegrationsView } from './components/PosIntegrationsView';
import { ItemFormModal } from './components/ItemFormModal';
import { ItemDetailsModal } from './components/ItemDetailsModal';
import { InventoryItem } from './types';
import { setStoredToken } from './services/api';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ActiveTab>('dashboard');
  const [tenantSlug, setTenantSlug] = useState<string>('green-grocer-downtown');

  // Modals
  const [showItemForm, setShowItemForm] = useState<boolean>(false);
  const [itemToEdit, setItemToEdit] = useState<InventoryItem | null>(null);
  const [selectedItemForDetails, setSelectedItemForDetails] = useState<InventoryItem | null>(null);

  // Key to force refresh of screens when data mutates
  const [refreshKey, setRefreshKey] = useState<number>(0);

  // Update tenant headers when switcher changes
  useEffect(() => {
    if (tenantSlug === 'green-grocer-downtown') {
      localStorage.setItem('test_tenant_id', 'tenant_a_green_grocer');
      localStorage.setItem('test_user_id', 'user_a_owner');
    } else {
      localStorage.setItem('test_tenant_id', 'tenant_b_artisan_bakery');
      localStorage.setItem('test_user_id', 'user_b_owner');
    }
    setRefreshKey((k) => k + 1);
  }, [tenantSlug]);

  const handleItemCreatedOrUpdated = (item: InventoryItem) => {
    setRefreshKey((k) => k + 1);
  };

  const handleOpenEdit = (item: InventoryItem) => {
    setItemToEdit(item);
    setShowItemForm(true);
  };

  const handleQuickAdjust = (item: InventoryItem) => {
    setSelectedItemForDetails(item);
  };

  return (
    <div className="app-container">
      {/* Navigation Sidebar */}
      <Navigation
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        tenantSlug={tenantSlug}
        setTenantSlug={setTenantSlug}
        onRefreshData={() => setRefreshKey((k) => k + 1)}
      />

      {/* Main Content Area */}
      <main className="main-content" key={refreshKey}>
        {activeTab === 'dashboard' && (
          <DashboardView
            onNavigate={(tab) => setActiveTab(tab)}
            onOpenCreateItem={() => {
              setItemToEdit(null);
              setShowItemForm(true);
            }}
          />
        )}

        {activeTab === 'inventory' && (
          <InventoryListView
            onSelectItem={(item) => setSelectedItemForDetails(item)}
            onOpenCreateItem={() => {
              setItemToEdit(null);
              setShowItemForm(true);
            }}
            onEditItem={handleOpenEdit}
            onQuickAdjust={handleQuickAdjust}
          />
        )}

        {activeTab === 'scanner' && (
          <div style={{ maxWidth: '600px', margin: '0 auto', width: '100%' }}>
            <BarcodeScanner
              authToken={localStorage.getItem('auth_token') || ''}
              onAdjustmentComplete={() => setRefreshKey((k) => k + 1)}
            />
          </div>
        )}

        {activeTab === 'expiry' && <ExpiryAlertsView />}

        {activeTab === 'csv' && <CsvImportView />}

        {activeTab === 'pos' && <PosIntegrationsView />}
      </main>

      {/* Item Create / Edit Modal */}
      {showItemForm && (
        <ItemFormModal
          itemToEdit={itemToEdit}
          onClose={() => {
            setShowItemForm(false);
            setItemToEdit(null);
          }}
          onSuccess={handleItemCreatedOrUpdated}
        />
      )}

      {/* Item Details & Stock Ledger Modal */}
      {selectedItemForDetails && (
        <ItemDetailsModal
          item={selectedItemForDetails}
          onClose={() => setSelectedItemForDetails(null)}
          onItemUpdated={handleItemCreatedOrUpdated}
        />
      )}
    </div>
  );
};

export default App;
