# frozen_string_literal: true

# Run with `bin/trmnlp test` (add `--report report` for a page of every screen drawn).
# Fixtures in tests/fixtures are real API responses; refresh them with `make fixtures`.
# Docs: https://github.com/usetrmnl/trmnlp/blob/main/docs/testing.md
require 'json'

FIXTURES = File.join(__dir__, 'fixtures')
API = 'https://pinball.trmnlplugins.com/*'

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

  %w[classic em long_name no_matches].each do |name|
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

  it 'hides everything optional without breaking' do
    hidden = %w[credits facts fun_fact tags same_year qr]
    expect(trmnl.render(device: 'og_png', mocks:, custom_fields: { 'hide_details' => hidden }))
      .to have_no_problems.and(have_no_leaked_text)
  end
end
