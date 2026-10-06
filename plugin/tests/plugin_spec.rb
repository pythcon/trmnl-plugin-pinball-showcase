# frozen_string_literal: true

# Run with `bin/trmnlp test` (add `--report report` for a page of every screen drawn).
# Fixtures in tests/fixtures are real API responses; refresh them with `make fixtures`.
# Docs: https://github.com/usetrmnl/trmnlp/blob/main/docs/testing.md
require 'json'

FIXTURES = File.join(__dir__, 'fixtures')
API = 'https://pinball-showcase.trmnlplugins.com/*'

def fixture(name) = JSON.parse(File.read(File.join(FIXTURES, "#{name}.json")))

# TRMNL's own screens plus the color (B/W/R/Y) OG.
SCREENS = [
  *TRMNLP::Testing::PUBLISHABLE_RECIPE_SCREENS,
  { device: 'og_bwry' }
].freeze
VIEWS = %w[full half_horizontal half_vertical quadrant].freeze

RSpec.describe 'Pinball Showcase' do
  let(:mocks) { { API => { json: fixture('modern') } } }
  let(:custom_fields) { {} }

  it_behaves_like 'a publishable recipe', screens: SCREENS

  %w[classic em square_art long_name borrowed_art alias_edition no_matches].each do |name|
    context "with the #{name} fixture" do
      VIEWS.each do |view|
        [{ device: 'og_png' }, { device: 'v2' }, { device: 'og_bwry' }].each do |screen|
          it "draws #{view} on #{screen[:device]} cleanly" do
            rendered = trmnl.render(view:, **screen, mocks: { API => { json: fixture(name) } }, custom_fields:)
            expect(rendered).to have_no_problems.and(have_no_leaked_text)
          end
        end
      end
    end
  end

  %w[gallery spec].each do |mode|
    context "in #{mode} mode" do
      let(:custom_fields) { { 'display_mode' => mode } }

      VIEWS.each do |view|
        it "draws #{view} on v2 cleanly" do
          expect(trmnl.render(view:, device: 'v2', mocks:, custom_fields:))
            .to have_no_problems.and(have_no_leaked_text)
        end
      end
    end
  end

  {
    'all three photos, filled, art on the right' => {
      'art_full' => %w[backglass playfield cabinet], 'art_half_horizontal' => %w[backglass playfield],
      'art_half_vertical' => %w[playfield cabinet], 'art_quadrant' => %w[cabinet], 'art_fit' => 'fill',
      'art_position' => 'right'
    },
    'text only everywhere' => {
      'art_full' => %w[none], 'art_half_horizontal' => %w[none], 'art_half_vertical' => %w[none],
      'art_quadrant' => %w[none]
    },
    'a photo the machine does not have' => { 'art_full' => %w[cabinet], 'art_quadrant' => %w[cabinet] }
  }.each do |label, fields|
    context "with #{label}" do
      VIEWS.each do |view|
        %w[og_png v2].each do |device|
          it "draws #{view} on #{device} cleanly" do
            fixture_name = label.include?('does not have') ? 'long_name' : 'modern'
            rendered = trmnl.render(view:, device:, mocks: { API => { json: fixture(fixture_name) } },
                                    custom_fields: fields)
            expect(rendered).to have_no_problems.and(have_no_leaked_text)
          end
        end
      end
    end
  end

  describe 'QR code' do
    # Scans the rendered screen: the code must decode to the machine's page on the site.
    page = 'https://pinball-showcase.trmnlplugins.com/m/GK17D-MdEqz'

    %w[og_png og_bwry v2].each do |device|
      it "links to the machine page on #{device}" do
        expect(trmnl.render(device:, mocks:)).to have_qr_code(page)
      end
    end

    %w[gallery spec].each do |mode|
      it "links to the machine page in #{mode} mode" do
        expect(trmnl.render(device: 'og_png', mocks:, custom_fields: { 'display_mode' => mode }))
          .to have_qr_code(page)
      end
    end
  end

  describe 'editions' do
    # Pirates CE has no photos: landscape slots borrow the standard backglass, the tall
    # half-vertical slot the LE's playfield.
    { 'full' => 'Standard', 'half_horizontal' => 'Standard', 'half_vertical' => 'LE',
      'quadrant' => 'Standard' }.each do |view, source|
      it "names the edition and whose art it borrows in #{view}" do
        rendered = trmnl.render(view:, device: 'og_bwry', mocks: { API => { json: fixture('borrowed_art') } })
        expect(rendered).to have_text('CE').and(have_text("Art from #{source}"))
      end
    end

    it 'lists the other editions, not the one on screen' do
      rendered = trmnl.render(device: 'og_png', mocks: { API => { json: fixture('alias_edition') } })
      expect(rendered).to have_text('Other editions').and(have_text('Wizard · Arcade'))
      expect(rendered).to have_no_text('Art from')
    end

    it 'shows no badge for a single-edition machine' do
      single = fixture('em')
      single['machine']['edition_label'] = nil
      single['editions'] = single['editions'].select { |e| e['shown'] }
      rendered = trmnl.render(device: 'og_png', mocks: { API => { json: single } })
      expect(rendered).to have_no_css('.label--inverted').and(have_no_text('Other editions'))
    end
  end

  it 'hides everything optional without breaking' do
    hidden = %w[credits facts fun_fact tags same_year qr]
    expect(trmnl.render(device: 'og_png', mocks:, custom_fields: { 'hide_details' => hidden }))
      .to have_no_problems.and(have_no_leaked_text)
  end
end
