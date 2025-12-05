import { Page } from '@playwright/test';
import { BasePage } from '../base/BasePage';
import { ServiceCard } from './components/ServiceCard';
import { VRAMMonitor } from './components/VRAMMonitor';

export class DashboardPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  getServiceCardByName(name: string): ServiceCard {
    return new ServiceCard(this.page, `.service-card:has(.service-name:text("${name}"))`);
  }

  getVRAMMonitor(): VRAMMonitor {
    return new VRAMMonitor(this.page, '.vram-monitor');
  }
}
